#!/bin/sh
# -----------------------------------------------------------------------------
# NetBSD System Configuration Script
# -----------------------------------------------------------------------------
# Purpose: Configure a fresh NetBSD installation for software development
# and web serving, following UNIX philosophy principles.
#
# Author: Inspired by Dennis M. Ritchie's approach to system administration
# License: BSD
# -----------------------------------------------------------------------------

set -e

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
LOG_FILE="/var/log/setup.log"
USERNAME="dmr"    # Historical nod to Dennis M. Ritchie

# Core development tools and libraries
PACKAGES="
    base-devel
    gcc
    clang
    make
    vim
    tmux
    git
    curl
    wget
    openssl
    openssh
    nginx
    sqlite3
    rsync
    htop
    lynx
"

# -----------------------------------------------------------------------------
# Logging function - simple and effective, as DMR would prefer
# -----------------------------------------------------------------------------
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG_FILE"
}

# -----------------------------------------------------------------------------
# Error handler - clean and straightforward
# -----------------------------------------------------------------------------
handle_error() {
    log "Error occurred at line $1"
    exit 1
}

trap 'handle_error $LINENO' ERR

# -----------------------------------------------------------------------------
# System package management
# -----------------------------------------------------------------------------
install_packages() {
    log "Updating package repository..."
    pkg_add -u

    log "Installing development packages..."
    for pkg in $PACKAGES; do
        if ! pkg_info | grep -q "^$pkg"; then
            pkg_add "$pkg"
            log "Installed: $pkg"
        fi
    done
}

# -----------------------------------------------------------------------------
# Configure SSH - security with simplicity
# -----------------------------------------------------------------------------
configure_ssh() {
    log "Configuring SSH..."

    cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak

    cat > /etc/ssh/sshd_config << EOF
Protocol 2
PermitRootLogin no
MaxAuthTries 6
PubkeyAuthentication yes
PasswordAuthentication no
PermitEmptyPasswords no
X11Forwarding no
EOF

    /etc/rc.d/sshd restart
}

# -----------------------------------------------------------------------------
# Configure development environment
# -----------------------------------------------------------------------------
setup_development() {
    log "Configuring development environment..."

    # Create development directories
    mkdir -p /home/$USERNAME/src
    mkdir -p /home/$USERNAME/bin

    # Set up basic .profile
    cat > /home/$USERNAME/.profile << EOF
PATH=\$HOME/bin:/bin:/sbin:/usr/bin:/usr/sbin:/usr/pkg/bin:/usr/local/bin
EDITOR=vi
PAGER=less
PS1='[\u@\h:\w]$ '
export PATH EDITOR PAGER PS1

alias ls='ls -F'
alias ll='ls -l'
alias h='history 25'
EOF

    # Set up minimal but effective vimrc
    cat > /home/$USERNAME/.vimrc << EOF
syntax on
set ai
set ruler
set background=dark
set showcmd
set showmatch
set incsearch
set tabstop=4
set shiftwidth=4
set expandtab
EOF

    chown -R $USERNAME:wheel /home/$USERNAME
}

# -----------------------------------------------------------------------------
# Configure web server (nginx)
# -----------------------------------------------------------------------------
configure_webserver() {
    log "Configuring nginx..."

    # Basic nginx configuration
    cat > /usr/pkg/etc/nginx/nginx.conf << EOF
worker_processes  1;
events {
    worker_connections  256;
}
http {
    include       mime.types;
    default_type  application/octet-stream;

    sendfile        on;
    keepalive_timeout  65;

    server {
        listen       80;
        server_name  localhost;
        root         /var/www/htdocs;

        location / {
            index  index.html;
        }
    }
}
EOF

    mkdir -p /var/www/htdocs
    echo "<html><body><h1>NetBSD Web Server</h1></body></html>" > /var/www/htdocs/index.html

    chmod -R 755 /var/www
    chown -R $USERNAME:wheel /var/www

    /etc/rc.d/nginx restart
}

# -----------------------------------------------------------------------------
# Configure system security
# -----------------------------------------------------------------------------
configure_security() {
    log "Configuring system security..."

    # Set secure defaults in /etc/sysctl.conf
    cat > /etc/sysctl.conf << EOF
net.inet.tcp.blackhole=2
net.inet.udp.blackhole=1
kern.securelevel=1
EOF

    # Update system settings
    sysctl -f /etc/sysctl.conf
}

# -----------------------------------------------------------------------------
# Main execution block
# -----------------------------------------------------------------------------
main() {
    log "Starting NetBSD system configuration..."

    if [ "$(id -u)" -ne 0 ]; then
        echo "This script must be run as root"
        exit 1
    fi

    # Create log file
    touch "$LOG_FILE"
    chmod 600 "$LOG_FILE"

    install_packages
    configure_ssh
    setup_development
    configure_webserver
    configure_security

    log "System configuration complete."
    log "Remember to run 'sync' before rebooting"
}

# Execute main function
main "$@"