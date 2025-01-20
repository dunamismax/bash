#!/usr/local/bin/bash
# ------------------------------------------------------------------------------
# FreeBSD Automated Setup Script
# ------------------------------------------------------------------------------
# Purpose: Automates fresh FreeBSD system configuration and maintenance tasks
# Version: 1.1.0
# Platform: FreeBSD 13.0+
# ------------------------------------------------------------------------------
#
# Features:
#  • Comprehensive system setup and configuration
#  • Robust error handling and logging
#  • Modular design with separate functions for each major task
#  • Configuration backup and restore capabilities
#  • Detailed logging with multiple verbosity levels
#
# Prerequisites:
#  • Root access or sudo privileges
#  • bash shell (will be installed if not present)
#  • Internet connection for package installation
#
# Usage:
#  $ sudo ./setup.sh [-v|--verbose] [-q|--quiet] [-h|--help] [-n|--dry-run]
#
# Options:
#  -v, --verbose     Increase output verbosity
#  -q, --quiet       Suppress all output except errors
#  -h, --help        Display this help message
#  -n, --dry-run     Show what would be done without making changes
#
# Exit Codes:
#  0  Success
#  1  General error
#  2  Invalid arguments
#  3  Insufficient privileges
#  4  System requirements not met
#
# Author: dunamismax
# License: MIT
# ------------------------------------------------------------------------------

# Strict mode settings
set -Eeuo pipefail
IFS=$'\n\t'

# ------------------------------------------------------------------------------
# Global Variables
# ------------------------------------------------------------------------------
readonly SCRIPT_VERSION="1.1.0"
readonly SCRIPT_NAME="${0##*/}"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
readonly OS_TYPE="$(uname -s)"
readonly OS_VERSION="$(uname -r)"

# Default configuration (can be overridden via command line or config file)
declare -A CONFIG=(
    [LOG_FILE]="/var/log/freebsd_setup.log"
    [VERBOSE]="1"
    [USERNAME]="sawyer"
    [BACKUP_DIR]="/var/backups/freebsd_setup"
    [CONFIG_FILE]="/usr/local/etc/freebsd_setup.conf"
    [DRY_RUN]="false"
)

# ------------------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------------------

usage() {
    cat << EOF
Usage: $SCRIPT_NAME [OPTIONS]

FreeBSD System Setup Script (Version: $SCRIPT_VERSION)
Automates the configuration and maintenance of FreeBSD systems.

Options:
  -v, --verbose     Increase output verbosity
  -q, --quiet       Suppress all output except errors
  -h, --help        Display this help message
  -n, --dry-run     Show what would be done without making changes
  -c, --config FILE Use specified config file

Examples:
  $SCRIPT_NAME --verbose
  $SCRIPT_NAME --config /path/to/config.conf
  $SCRIPT_NAME --dry-run

For complete documentation, visit:
https://github.com/dunamismax/freebsd-setup
EOF
    exit 0
}

# ------------------------------------------------------------------------------
# System Validation Functions
# ------------------------------------------------------------------------------

check_system_requirements() {
    local -r MIN_FreeBSD_VERSION="13.0"

    # Verify we're running on FreeBSD
    if [[ "$OS_TYPE" != "FreeBSD" ]]; then
        log ERROR "This script is designed for FreeBSD systems only. Detected: $OS_TYPE"
        exit 4
    }

    # Check FreeBSD version
    if ! printf '%s\n%s\n' "$MIN_FreeBSD_VERSION" "$OS_VERSION" | sort -C -V; then
        log ERROR "FreeBSD version $MIN_FreeBSD_VERSION or higher is required. Detected: $OS_VERSION"
        exit 4
    }

    # Check for root privileges
    if [[ $EUID -ne 0 ]]; then
        log ERROR "This script must be run as root or with sudo"
        exit 3
    }

    # Check for required commands
    local -r REQUIRED_COMMANDS=(pkg bash)
    for cmd in "${REQUIRED_COMMANDS[@]}"; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            log ERROR "Required command not found: $cmd"
            exit 4
        fi
    }

    # Check internet connectivity
    if ! ping -c 1 8.8.8.8 >/dev/null 2>&1; then
        log WARN "No internet connectivity detected. Some features may not work."
    }

    log INFO "System requirements check passed"
}

# ------------------------------------------------------------------------------
# Enhanced Logging Function
# ------------------------------------------------------------------------------

log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")

    # Define color codes
    local RED='\033[0;31m'
    local YELLOW='\033[0;33m'
    local GREEN='\033[0;32m'
    local BLUE='\033[0;34m'
    local BOLD='\033[1m'
    local NC='\033[0m'

    # Validate log level and set color
    case "${level^^}" in
        INFO)
            local color="${GREEN}"
            local priority="6"
            ;;
        WARN|WARNING)
            local color="${YELLOW}"
            local priority="4"
            level="WARN"
            ;;
        ERROR)
            local color="${RED}"
            local priority="3"
            ;;
        DEBUG)
            local color="${BLUE}"
            local priority="7"
            ;;
        *)
            local color="${NC}"
            local priority="6"
            level="INFO"
            ;;
    esac

    # Format the log entry
    local log_entry="[$timestamp] [${level}] [$$] $message"

    # Write to system log if available
    if command -v logger >/dev/null 2>&1; then
        logger -p "local0.${priority}" -t "${SCRIPT_NAME}[$$]" "$message"
    fi

    # Ensure log directory exists and is writable
    local log_dir
    log_dir="$(dirname "${CONFIG[LOG_FILE]}")"
    if [[ ! -d "$log_dir" ]]; then
        mkdir -p "$log_dir"
        chmod 755 "$log_dir"
    fi

    # Append to log file
    echo "$log_entry" >> "${CONFIG[LOG_FILE]}"

    # Console output based on verbosity and log level
    if [[ "${CONFIG[VERBOSE]}" -ge 2 ]] || \
       [[ "${CONFIG[VERBOSE]}" -ge 1 && "$level" == "ERROR" ]] || \
       [[ "${CONFIG[VERBOSE]}" -ge 1 && "$level" == "WARN" ]]; then
        printf "${color}%s${NC}\n" "$log_entry" >&2
    fi
}

# ------------------------------------------------------------------------------
# Error Handling
# ------------------------------------------------------------------------------

cleanup() {
    local exit_code=$?
    log DEBUG "Cleanup started (Exit Code: $exit_code)"

    # Remove temporary files
    if [[ -d "$tmp_dir" ]]; then
        rm -rf "$tmp_dir"
        log DEBUG "Removed temporary directory: $tmp_dir"
    }

    # Reset terminal
    tput sgr0

    exit "$exit_code"
}

handle_error() {
    local line_no=$1
    local error_code=$2
    local last_command="${BASH_COMMAND}"

    log ERROR "Error in line ${line_no}: Command '${last_command}' exited with status ${error_code}"

    # Additional error context
    log DEBUG "Stack trace:"
    local frame=0
    while caller $frame; do
        ((frame++))
    done | awk '{printf "  %s:%d in function %s\n", $3, $1, $2}' >> "${CONFIG[LOG_FILE]}"
}

# Set up error traps
trap 'handle_error ${LINENO} $?' ERR
trap cleanup EXIT

# ------------------------------------------------------------------------------
# Backup Function
# ------------------------------------------------------------------------------

backup_system() {
    log INFO "Starting backup preparation"

    # Ensure rsync is installed
    if ! command -v rsync >/dev/null 2>&1; then
        log INFO "Installing rsync..."
        if ! pkg install -y rsync; then
            log ERROR "Failed to install rsync"
            return 1
        fi
    fi

    # Configuration
    local -r SOURCE="/"
    local -r DESTINATION="${CONFIG[BACKUP_DIR]:-/home/${CONFIG[USERNAME]}/BACKUPS}"
    local -r TIMESTAMP="$(date +"%Y-%m-%d_%H-%M-%S")"
    local -r BACKUP_FOLDER="$DESTINATION/backup-$TIMESTAMP"
    local -r RETENTION_DAYS="${CONFIG[BACKUP_RETENTION_DAYS]:-7}"
    local -r LOCK_FILE="/var/run/freebsd_backup.lock"

    # FreeBSD-specific excludes
    local -r EXCLUDES=(
        "/proc/*" "/dev/*" "/tmp/*" "/mnt/*" "/media/*"
        "/var/tmp/*" "/var/cache/*" "/var/log/*"
        "/var/run/*" "/var/lib/docker/*"
        "/root/.cache/*" "/home/*/.cache/*"
        "/usr/ports/*" "/usr/src/*"
        "/boot/kernel.old/*"
        "$DESTINATION"
    )

    # Prevent multiple backup processes
    if [[ -f "$LOCK_FILE" ]]; then
        local pid
        pid=$(cat "$LOCK_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            log ERROR "Another backup process (PID: $pid) is already running"
            return 1
        else
            log WARN "Removing stale lock file"
            rm -f "$LOCK_FILE"
        fi
    fi
    echo $ > "$LOCK_FILE"

    # Ensure backup destination exists
    if ! mkdir -p "$BACKUP_FOLDER"; then
        log ERROR "Failed to create backup directory: $BACKUP_FOLDER"
        rm -f "$LOCK_FILE"
        return 1
    fi

    # Prepare rsync exclude arguments
    local EXCLUDES_ARGS=()
    for EXCLUDE in "${EXCLUDES[@]}"; do
        EXCLUDES_ARGS+=(--exclude="$EXCLUDE")
    done

    # Add backup metadata
    {
        echo "Backup created on: $(date)"
        echo "FreeBSD version: $(uname -a)"
        echo "Installed packages:"
        pkg info
        echo "Disk usage:"
        df -h
    } > "$BACKUP_FOLDER/backup-metadata.txt"

    # Perform backup with progress monitoring
    log INFO "Starting system backup to $BACKUP_FOLDER"
    if [[ "${CONFIG[DRY_RUN]}" == "true" ]]; then
        log INFO "[DRY RUN] Would backup system to: $BACKUP_FOLDER"
        rsync --dry-run -aAXv --progress "${EXCLUDES_ARGS[@]}" "$SOURCE" "$BACKUP_FOLDER"
    else
        if rsync -aAXv --progress "${EXCLUDES_ARGS[@]}" "$SOURCE" "$BACKUP_FOLDER"; then
            log INFO "Backup completed successfully: $BACKUP_FOLDER"
            # Create success flag file
            touch "$BACKUP_FOLDER/.backup_complete"
        else
            log ERROR "Backup process failed"
            rm -rf "$BACKUP_FOLDER"
            rm -f "$LOCK_FILE"
            return 1
        fi
    fi

    # Cleanup old backups
    log INFO "Cleaning up backups older than $RETENTION_DAYS days"
    if [[ "${CONFIG[DRY_RUN]}" == "true" ]]; then
        log INFO "[DRY RUN] Would remove backups older than $RETENTION_DAYS days"
        find "$DESTINATION" -type d -name "backup-*" -mtime +"$RETENTION_DAYS" -print
    else
        if find "$DESTINATION" -type d -name "backup-*" -mtime +"$RETENTION_DAYS" -exec rm -rf {} \;; then
            log INFO "Old backups removed successfully"
        else
            log WARN "Failed to remove some old backups"
        fi
    fi

    rm -f "$LOCK_FILE"
    return 0
}

# ------------------------------------------------------------------------------
# Package Installation Function
# ------------------------------------------------------------------------------

install_pkgs() {
    log INFO "Starting package installation process"

    # Update package repository and upgrade existing packages
    log INFO "Updating pkg repositories and upgrading existing packages..."
    if [[ "${CONFIG[DRY_RUN]}" != "true" ]]; then
        if ! pkg update && pkg upgrade -y; then
            log ERROR "System upgrade failed"
            return 1
        fi
    fi

    # Define package categories and their contents
    declare -A PACKAGE_GROUPS=(
        [development]="gcc cmake git pkgconf openssl llvm autoconf automake libtool ninja meson gettext
                      gmake valgrind doxygen ccache diffutils"

        [system_utils]="bash zsh fish nano screen tmate mosh htop iftop tree wget curl rsync unzip
                       zip ca_root_nss sudo less neovim mc jq pigz fzf lynx smartmontools
                       neofetch screenfetch ncdu dos2unix figlet toilet ripgrep"

        [libraries]="libffi readline sqlite3 ncurses gdbm nss lzma libxml2"

        [network_security]="nmap netcat socat tcpdump wireshark aircrack-ng john hydra openvpn
                          ipmitool bmon whois bind-tools"

        [languages]="python39 go ruby perl5 rust node npm"

        [virtualization]="docker vagrant qemu"

        [web_servers]="nginx postgresql15-server postgresql15-client"

        [monitoring]="syslog-ng grafana prometheus netdata"

        [misc]="lsof bsdstats rclone"
    )

    # Function to install package group
    install_group() {
        local group=$1
        local packages=($2)

        log INFO "Installing $group packages..."
        if [[ "${CONFIG[DRY_RUN]}" == "true" ]]; then
            log INFO "[DRY RUN] Would install packages: ${packages[*]}"
            return 0
        fi

        local failed_pkgs=()
        for pkg in "${packages[@]}"; do
            if ! pkg install -y "$pkg"; then
                failed_pkgs+=("$pkg")
                log WARN "Failed to install package: $pkg"
            fi
        done

        if [[ ${#failed_pkgs[@]} -gt 0 ]]; then
            log WARN "Failed to install the following packages: ${failed_pkgs[*]}"
            return 1
        fi

        return 0
    }

    # Install each package group
    local failed_groups=()
    for group in "${!PACKAGE_GROUPS[@]}"; do
        if ! install_group "$group" "${PACKAGE_GROUPS[$group]}"; then
            failed_groups+=("$group")
        fi
    done

    # Install additional development tools
    if [[ "${CONFIG[DRY_RUN]}" != "true" ]]; then
        # Install Rust toolchain
        log INFO "Installing Rust toolchain via rustup..."
        if ! curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y; then
            log ERROR "Failed to install Rust toolchain"
            failed_groups+=("rust_toolchain")
        fi
        export PATH="$HOME/.cargo/bin:$PATH"

        # Verify Go installation
        if ! command -v go >/dev/null 2>&1; then
            log INFO "Installing Go..."
            if ! pkg install -y go; then
                log ERROR "Failed to install Go"
                failed_groups+=("go")
            fi
        fi
    fi

    # Report results
    if [[ ${#failed_groups[@]} -gt 0 ]]; then
        log WARN "The following package groups had installation failures: ${failed_groups[*]}"
        return 1
    else
        log INFO "All package installations completed successfully"
        return 0
    fi
}

# ------------------------------------------------------------------------------
# SSH Configuration Function
# ------------------------------------------------------------------------------

configure_ssh_settings() {
    log INFO "Configuring OpenSSH Server"

    # Install OpenSSH if not present
    if ! pkg info openssh-portable >/dev/null 2>&1; then
        log INFO "Installing OpenSSH Server..."
        if [[ "${CONFIG[DRY_RUN]}" != "true" ]] && ! pkg install -y openssh-portable; then
            log ERROR "Failed to install OpenSSH Server"
            return 1
        fi
    fi

    # Define paths
    local -r SSHD_CONFIG="/usr/local/etc/ssh/sshd_config"
    local -r SSHD_CONFIG_DIR="/usr/local/etc/ssh/sshd_config.d"
    local -r MODULI_FILE="/usr/local/etc/ssh/moduli"
    local -r BACKUP_SUFFIX=".bak.$(date +%Y%m%d%H%M%S)"

    # Create backup
    if [[ -f "$SSHD_CONFIG" && "${CONFIG[DRY_RUN]}" != "true" ]]; then
        cp "$SSHD_CONFIG" "${SSHD_CONFIG}${BACKUP_SUFFIX}"
        log INFO "Created backup of sshd_config at ${SSHD_CONFIG}${BACKUP_SUFFIX}"
    fi

    # Create modern sshd configuration
    local ssh_config_content
    read -r -d '' ssh_config_content << 'EOF'
# This is the sshd server system-wide configuration file.
# Created by FreeBSD setup script on $(date)

# Logging
SyslogFacility AUTH
LogLevel VERBOSE

# Authentication
PermitRootLogin no
MaxAuthTries 3
MaxSessions 10
PubkeyAuthentication yes
PasswordAuthentication no
PermitEmptyPasswords no
ChallengeResponseAuthentication no
UsePAM no
AuthenticationMethods publickey

# Network
Port 22
AddressFamily any
ListenAddress 0.0.0.0
ListenAddress ::
Protocol 2
TCPKeepAlive yes
ClientAliveInterval 300
ClientAliveCountMax 2

# Security
HostKey /usr/local/etc/ssh/ssh_host_ed25519_key
HostKey /usr/local/etc/ssh/ssh_host_rsa_key
KexAlgorithms curve25519-sha256@libssh.org,diffie-hellman-group16-sha512,diffie-hellman-group18-sha512
Ciphers chacha20-poly1305@openssh.com,aes256-gcm@openssh.com,aes128-gcm@openssh.com
MACs hmac-sha2-512-etm@openssh.com,hmac-sha2-256-etm@openssh.com
HostKeyAlgorithms ssh-ed25519,rsa-sha2-512,rsa-sha2-256

# Features
X11Forwarding no
AllowTcpForwarding no
AllowAgentForwarding no
PermitTunnel no
PrintMotd no
UseDNS no
PermitUserEnvironment no

# Accept locale-related environment variables
AcceptEnv LANG LC_*

# Subsystem
Subsystem sftp internal-sftp

# Allow only specific groups to connect
AllowGroups wheel

# Enable this for more logs during troubleshooting
#LogLevel DEBUG3
EOF

    if [[ "${CONFIG[DRY_RUN]}" == "true" ]]; then
        log INFO "[DRY RUN] Would write new sshd_config:"
        echo "$ssh_config_content"
    else
        # Create config directory if it doesn't exist
        mkdir -p "$SSHD_CONFIG_DIR"

        # Write new configuration
        echo "$ssh_config_content" > "$SSHD_CONFIG"
        chmod 600 "$SSHD_CONFIG"

        # Enable and restart sshd
        if ! sysrc sshd_enable="YES" >/dev/null 2>&1; then
            log ERROR "Failed to enable sshd in rc.conf"
            return 1
        fi

        # Test configuration before restarting
        if ! /usr/local/sbin/sshd -t -f "$SSHD_CONFIG"; then
            log ERROR "SSH configuration test failed"
            return 1
        fi

        if ! service sshd restart; then
            log ERROR "Failed to restart sshd service"
            return 1
        fi
    fi

    log INFO "SSH configuration completed successfully"
    return 0
}

# ------------------------------------------------------------------------------
# Caddy Installation and Configuration Function
# ------------------------------------------------------------------------------

install_caddy() {
    log INFO "Starting Caddy installation and configuration"

    # Check for prerequisites
    if ! command -v fetch >/dev/null 2>&1; then
        log ERROR "fetch utility not found. Cannot proceed with installation"
        return 1
    fi

    # Define paths and versions
    local -r CADDY_USER="www"
    local -r CADDY_GROUP="www"
    local -r CADDY_CONFIG_DIR="/usr/local/etc/caddy"
    local -r CADDY_DATA_DIR="/var/lib/caddy"
    local -r CADDY_CONFIG="${CADDY_CONFIG_DIR}/Caddyfile"

    # Install Caddy if not present
    if ! pkg info caddy >/dev/null 2>&1; then
        log INFO "Installing Caddy via pkg..."
        if [[ "${CONFIG[DRY_RUN]}" != "true" ]] && ! pkg install -y caddy; then
            log ERROR "Failed to install Caddy"
            return 1
        fi
    else
        log INFO "Caddy is already installed"
    fi

    if [[ "${CONFIG[DRY_RUN]}" != "true" ]]; then
        # Create necessary directories
        for dir in "$CADDY_CONFIG_DIR" "$CADDY_DATA_DIR"; do
            if ! mkdir -p "$dir"; then
                log ERROR "Failed to create directory: $dir"
                return 1
            fi
        done

        # Set up default Caddyfile if it doesn't exist
        if [[ ! -f "$CADDY_CONFIG" ]]; then
            cat > "$CADDY_CONFIG" << 'EOF'
# Global options
{
    admin off  # Disable admin interface for security
    persist_config off  # Don't persist config to disk
    auto_https off  # Disable automatic HTTPS
    log {
        output file /var/log/caddy/access.log
        format json
    }
}

# Default site
:80 {
    root * /usr/local/www/caddy
    file_server
    encode gzip

    # Basic security headers
    header {
        -Server
        Strict-Transport-Security "max-age=31536000;"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "no-referrer-when-downgrade"
    }

    # Health check endpoint
    respond /health 200

    # Error handling
    handle_errors {
        respond "{http.error.status_code} {http.error.status_text}" {http.error.status_code}
    }
}
EOF
            chmod 644 "$CADDY_CONFIG"
        fi

        # Create log directory
        mkdir -p /var/log/caddy
        chown -R "$CADDY_USER:$CADDY_GROUP" /var/log/caddy

        # Set correct permissions
        chown -R "$CADDY_USER:$CADDY_GROUP" "$CADDY_CONFIG_DIR" "$CADDY_DATA_DIR"
        chmod 755 "$CADDY_CONFIG_DIR" "$CADDY_DATA_DIR"

        # Enable and start Caddy service
        if ! sysrc caddy_enable="YES" >/dev/null 2>&1; then
            log ERROR "Failed to enable Caddy in rc.conf"
            return 1
        fi

        # Validate configuration
        if ! caddy validate --config "$CADDY_CONFIG" >/dev/null 2>&1; then
            log ERROR "Caddy configuration validation failed"
            return 1
        fi

        # Start/restart Caddy service
        if ! service caddy restart; then
            log ERROR "Failed to start Caddy service"
            return 1
        fi
    fi

    log INFO "Caddy installation and configuration completed successfully"
    return 0
}

# ------------------------------------------------------------------------------
# Plex Media Server Installation Function
# ------------------------------------------------------------------------------

install_and_enable_plex() {
    log INFO "Starting Plex Media Server installation"

    local -r PLEX_USER="plex"
    local -r PLEX_GROUP="plex"
    local -r PLEX_CONFIG_DIR="/usr/local/plexdata"
    local -r PLEX_MEDIA_DIR="/usr/local/plexmedia"
    local -r PLEX_TRANSCODE_DIR="/usr/local/plexdata/transcode"

    # Install Plex if not present
    if ! pkg info plexmediaserver >/dev/null 2>&1; then
        log INFO "Installing Plex Media Server..."
        if [[ "${CONFIG[DRY_RUN]}" != "true" ]] && ! pkg install -y plexmediaserver; then
            log ERROR "Failed to install Plex Media Server"
            return 1
        fi
    else
        log INFO "Plex Media Server is already installed"
    fi

    if [[ "${CONFIG[DRY_RUN]}" != "true" ]]; then
        # Create necessary directories
        for dir in "$PLEX_CONFIG_DIR" "$PLEX_MEDIA_DIR" "$PLEX_TRANSCODE_DIR"; do
            if ! mkdir -p "$dir"; then
                log ERROR "Failed to create directory: $dir"
                return 1
            fi
        done

        # Set correct permissions
        chown -R "$PLEX_USER:$PLEX_GROUP" "$PLEX_CONFIG_DIR" "$PLEX_MEDIA_DIR"
        chmod 755 "$PLEX_CONFIG_DIR" "$PLEX_MEDIA_DIR"

        # Configure Plex service
        local plex_rc_config=(
            "plexmediaserver_enable=YES"
            "plexmediaserver_support_path=$PLEX_CONFIG_DIR"
            "plexmediaserver_tmp=$PLEX_TRANSCODE_DIR"
            "plexmediaserver_user=$PLEX_USER"
            "plexmediaserver_group=$PLEX_GROUP"
        )

        # Add configurations to rc.conf
        for config in "${plex_rc_config[@]}"; do
            if ! sysrc "$config" >/dev/null 2>&1; then
                log ERROR "Failed to set rc.conf configuration: $config"
                return 1
            fi
        done

        # Start Plex service
        if ! service plexmediaserver restart; then
            log ERROR "Failed to start Plex Media Server service"
            return 1
        fi
    fi

    log INFO "Plex Media Server installation completed successfully"
    log INFO "Access your server at: http://localhost:32400/web"
    return 0
}

# ------------------------------------------------------------------------------
# Zig Installation Function
# ------------------------------------------------------------------------------

install_zig() {
    log INFO "Starting Zig installation"

    # Check if Zig is already installed
    if command -v zig >/dev/null 2>&1; then
        local current_version
        current_version=$(zig version)
        log INFO "Zig is already installed (Version: $current_version)"
        return 0
    fi

    # Configuration
    local -r ZIG_VERSION="${CONFIG[ZIG_VERSION]:-0.11.0}"
    local -r ZIG_INSTALL_DIR="/usr/local/zig"
    local -r TMP_DIR=$(mktemp -d)
    local -r ZIG_TARBALL="${TMP_DIR}/zig.tar.xz"
    local -r ZIG_URL="https://ziglang.org/builds/zig-freebsd-x86_64-${ZIG_VERSION}.tar.xz"

    # Cleanup handler
    trap 'rm -rf "$TMP_DIR"' EXIT

    if [[ "${CONFIG[DRY_RUN]}" != "true" ]]; then
        # Download Zig
        log INFO "Downloading Zig ${ZIG_VERSION}..."
        if ! fetch -o "$ZIG_TARBALL" "$ZIG_URL"; then
            log ERROR "Failed to download Zig"
            return 1
        fi

        # Verify download
        if [[ ! -f "$ZIG_TARBALL" ]]; then
            log ERROR "Downloaded file not found: $ZIG_TARBALL"
            return 1
        fi

        # Extract archive
        log INFO "Extracting Zig archive..."
        if ! tar xf "$ZIG_TARBALL" -C "$TMP_DIR"; then
            log ERROR "Failed to extract Zig archive"
            return 1
        fi

        # Find extracted directory
        local extracted_dir
        extracted_dir=$(find "$TMP_DIR" -maxdepth 1 -type d -name "zig-*" | head -n1)
        if [[ -z "$extracted_dir" ]]; then
            log ERROR "Could not find extracted Zig directory"
            return 1
        fi

        # Install Zig
        log INFO "Installing Zig to $ZIG_INSTALL_DIR..."
        rm -rf "$ZIG_INSTALL_DIR"
        if ! mv "$extracted_dir" "$ZIG_INSTALL_DIR"; then
            log ERROR "Failed to move Zig to installation directory"
            return 1
        fi

        # Create symlink
        log INFO "Creating Zig symlink..."
        ln -sf "$ZIG_INSTALL_DIR/zig" /usr/local/bin/zig
        chmod +x /usr/local/bin/zig

        # Verify installation
        if ! zig version >/dev/null 2>&1; then
            log ERROR "Zig installation verification failed"
            return 1
        fi
    fi

    log INFO "Zig installation completed successfully"
    return 0
}

# ------------------------------------------------------------------------------
# VSCode CLI Installation Function
# ------------------------------------------------------------------------------

install_vscode_cli() {
    log INFO "Starting VS Code CLI installation"

    local -r VSCODE_DIR="/usr/local/vscode-cli"
    local -r TMP_DIR=$(mktemp -d)
    local -r CLI_TARBALL="${TMP_DIR}/vscode_cli.tar.gz"
    local -r CLI_URL="https://code.visualstudio.com/sha/download?build=stable&os=cli-alpine-x64"

    # Cleanup handler
    trap 'rm -rf "$TMP_DIR"' EXIT

    # Ensure Node.js is installed
    if ! command -v node >/dev/null 2>&1; then
        log ERROR "Node.js is required but not installed"
        return 1
    fi

    if [[ "${CONFIG[DRY_RUN]}" != "true" ]]; then
        # Create installation directory
        mkdir -p "$VSCODE_DIR"

        # Download CLI
        log INFO "Downloading VS Code CLI..."
        if ! fetch -o "$CLI_TARBALL" "$CLI_URL"; then
            log ERROR "Failed to download VS Code CLI"
            return 1
        fi

        # Extract CLI
        log INFO "Extracting VS Code CLI..."
        if ! tar -xzf "$CLI_TARBALL" -C "$VSCODE_DIR"; then
            log ERROR "Failed to extract VS Code CLI"
            return 1
        fi

        # Set permissions
        chmod +x "$VSCODE_DIR/code"

        # Create symlink
        ln -sf "$VSCODE_DIR/code" /usr/local/bin/code-tunnel

        # Create Node.js symlink if needed
        if [[ ! -e "/usr/local/node" ]]; then
            ln -sf "$(command -v node)" /usr/local/node
        fi
    fi

    log INFO "VS Code CLI installation completed successfully"
    log INFO "Use 'code-tunnel tunnel --name YOUR-MACHINE-NAME' to start the tunnel"
    return 0
}

# ------------------------------------------------------------------------------
# Font Installation Function
# ------------------------------------------------------------------------------

install_font() {
    log INFO "Starting font installation"

    # Configuration
    local -r FONT_URL="https://github.com/ryanoasis/nerd-fonts/raw/master/patched-fonts/FiraCode/Regular/FiraCodeNerdFont-Regular.ttf"
    local -r FONT_DIR="/usr/local/share/fonts/nerd-fonts"
    local -r FONT_FILE="FiraCodeNerdFont-Regular.ttf"
    local -r TMP_DIR=$(mktemp -d)

    # Cleanup handler
    trap 'rm -rf "$TMP_DIR"' EXIT

    # Ensure required packages are installed
    if ! pkg info fontconfig >/dev/null 2>&1; then
        log INFO "Installing fontconfig..."
        if [[ "${CONFIG[DRY_RUN]}" != "true" ]] && ! pkg install -y fontconfig; then
            log ERROR "Failed to install fontconfig"
            return 1
        fi
    fi

    if [[ "${CONFIG[DRY_RUN]}" != "true" ]]; then
        # Create font directory
        mkdir -p "$FONT_DIR"

        # Download font
        log INFO "Downloading Nerd Font..."
        if ! fetch -o "${TMP_DIR}/${FONT_FILE}" "$FONT_URL"; then
            log ERROR "Failed to download font"
            return 1
        fi

        # Install font
        if ! mv "${TMP_DIR}/${FONT_FILE}" "${FONT_DIR}/${FONT_FILE}"; then
            log ERROR "Failed to install font"
            return 1
        fi

        # Set permissions
        chmod 644 "${FONT_DIR}/${FONT_FILE}"

        # Update font cache
        log INFO "Updating font cache..."
        if ! fc-cache -f "$FONT_DIR"; then
            log ERROR "Failed to update font cache"
            return 1
        fi
    fi

    log INFO "Font installation completed successfully"
    return 0
}

# ------------------------------------------------------------------------------
# Repository Management Functions
# ------------------------------------------------------------------------------

download_repositories() {
    local -r GITHUB_USERNAME="${CONFIG[GITHUB_USERNAME]:-dunamismax}"
    local -r GITHUB_DIR="/home/${CONFIG[USERNAME]}/github"

    # List of repositories to manage
    local -ra REPOS=(
        "bash"
        "c"
        "religion"
        "windows"
        "hugo"
        "python"
    )

    log INFO "Starting repository management for user: $GITHUB_USERNAME"

    # Create GitHub directory if it doesn't exist
    if [[ ! -d "$GITHUB_DIR" ]]; then
        log INFO "Creating GitHub directory: $GITHUB_DIR"
        if ! mkdir -p "$GITHUB_DIR"; then
            log ERROR "Failed to create GitHub directory"
            return 1
        fi
    fi

    # Track failures
    local failed_repos=()

    # Change to GitHub directory
    if ! cd "$GITHUB_DIR"; then
        log ERROR "Failed to access GitHub directory: $GITHUB_DIR"
        return 1
    fi

    # Clone or update repositories
    for repo in "${REPOS[@]}"; do
        if [[ "${CONFIG[DRY_RUN]}" == "true" ]]; then
            log INFO "[DRY RUN] Would process repository: $repo"
            continue
        fi

        log INFO "Processing repository: $repo"

        if [[ -d "$repo/.git" ]]; then
            log INFO "Repository exists, updating: $repo"
            if ! (cd "$repo" && git fetch && git reset --hard origin/main); then
                log ERROR "Failed to update repository: $repo"
                failed_repos+=("$repo")
                continue
            fi
        else
            log INFO "Cloning new repository: $repo"
            if [[ -d "$repo" ]]; then
                log INFO "Removing existing non-git directory: $repo"
                rm -rf "$repo"
            fi

            if ! git clone "https://github.com/$GITHUB_USERNAME/${repo}.git"; then
                log ERROR "Failed to clone repository: $repo"
                failed_repos+=("$repo")
                continue
            fi
        fi

        # Set repository permissions
        set_repo_permissions "$repo"
    done

    # Return to original directory
    cd - >/dev/null || true

    # Report results
    if [[ ${#failed_repos[@]} -gt 0 ]]; then
        log WARN "Failed to process repositories: ${failed_repos[*]}"
        return 1
    fi

    log INFO "Repository management completed successfully"
    return 0
}

# ------------------------------------------------------------------------------
# Permission Management Functions
# ------------------------------------------------------------------------------

set_repo_permissions() {
    local repo=$1
    local -r GITHUB_DIR="/home/${CONFIG[USERNAME]}/github"

    [[ -z "$repo" ]] && {
        log ERROR "Repository name not provided"
        return 1
    }

    if [[ "${CONFIG[DRY_RUN]}" == "true" ]]; then
        log INFO "[DRY RUN] Would set permissions for: $repo"
        return 0
    }

    log INFO "Setting permissions for repository: $repo"

    # Hugo-specific permissions
    if [[ "$repo" == "hugo" ]]; then
        local -r HUGO_PUBLIC="$GITHUB_DIR/hugo/dunamismax.com/public"
        local -r HUGO_BASE="$GITHUB_DIR/hugo"

        if [[ -d "$HUGO_PUBLIC" ]]; then
            log INFO "Setting Hugo public directory permissions"
            chown -R www:www "$HUGO_PUBLIC"
            chmod -R 755 "$HUGO_PUBLIC"
        fi

        if [[ -d "$HUGO_BASE" ]]; then
            log INFO "Setting Hugo base directory permissions"
            chown -R sawyer:sawyer "$HUGO_BASE"
            chmod -R u=rwX,g=rX,o=rX "$HUGO_BASE"

            # Ensure path to Hugo is accessible
            chmod o+rx "/home/${CONFIG[USERNAME]}" "$GITHUB_DIR" \
                      "$HUGO_BASE" "$HUGO_BASE/dunamismax.com"
        fi
    else
        # Standard repository permissions
        chown -R "${CONFIG[USERNAME]}:${CONFIG[USERNAME]}" "$GITHUB_DIR/$repo"
        chmod -R u=rwX,g=rX,o= "$GITHUB_DIR/$repo"
    fi

    return 0
}

set_directory_permissions() {
    local -r BASE_DIR="/home/${CONFIG[USERNAME]}/github"
    local -r HOME_DIR="/home/${CONFIG[USERNAME]}"

    log INFO "Starting directory permission management"

    if [[ "${CONFIG[DRY_RUN]}" == "true" ]]; then
        log INFO "[DRY RUN] Would set directory permissions"
        return 0
    }

    # Verify base directory exists
    if [[ ! -d "$BASE_DIR" ]]; then
        log ERROR "Base directory does not exist: $BASE_DIR"
        return 1
    }

    # Make shell scripts executable
    log INFO "Setting executable permissions for shell scripts"
    find "$BASE_DIR" -type f -name "*.sh" -exec chmod +x {} \;

    # Set base ownership
    log INFO "Setting base directory ownership"
    chown -R "${CONFIG[USERNAME]}:${CONFIG[USERNAME]}" "$HOME_DIR"

    # Process git directories
    log INFO "Setting Git directory permissions"
    while IFS= read -r -d '' git_dir; do
        set_git_permissions "$git_dir"
    done < <(find "$BASE_DIR" -type d -name ".git" -print0)

    log INFO "Directory permission management completed"
    return 0
}

set_git_permissions() {
    local git_dir=$1

    [[ -z "$git_dir" ]] && {
        log ERROR "Git directory not provided"
        return 1
    }

    if [[ "${CONFIG[DRY_RUN]}" == "true" ]]; then
        log INFO "[DRY RUN] Would set Git permissions for: $git_dir"
        return 0
    }

    log INFO "Setting Git permissions for: $git_dir"

    # Set directory permissions (rwx for owner only)
    chmod 700 "$git_dir"

    # Set permissions for subdirectories
    find "$git_dir" -type d -exec chmod 700 {} \;

    # Set permissions for files (rw for owner only)
    find "$git_dir" -type f -exec chmod 600 {} \;

    return 0
}

# ------------------------------------------------------------------------------
# Firewall Configuration Function
# ------------------------------------------------------------------------------

configure_pf() {
    log INFO "Starting PF firewall configuration"

    local -r PF_CONF="/etc/pf.conf"
    local -r BACKUP_CONF="/etc/pf.conf.bak.$(date +%Y%m%d%H%M%S)"
    local -r INTERFACE="${CONFIG[NETWORK_INTERFACE]:-em0}"

    # Backup existing configuration
    if [[ -f "$PF_CONF" && "${CONFIG[DRY_RUN]}" != "true" ]]; then
        cp "$PF_CONF" "$BACKUP_CONF" || {
            log ERROR "Failed to create backup of PF configuration"
            return 1
        }
    fi

    # Create new PF configuration
    local pf_config
    read -r -d '' pf_config << EOF
# PF configuration for FreeBSD
# Generated by setup script on $(date)

# Macros
ext_if = "$INTERFACE"
tcp_services = "{ ssh http https 8080 32400 8324 32469 }"
udp_services = "{ domain ntp 1900 5353 32410:32415 }"

# Tables for dynamic blocking
table <bruteforce> persist
table <ddos> persist
table <blacklist> persist file "/etc/pf.blacklist"

# Options
set skip on lo
set block-policy drop
set debug info
set limit { states 100000, frags 20000, src-nodes 10000 }
set optimization aggressive
set ruleset-optimization basic

# Normalization
scrub in all no-df fragment reassemble max-mss 1440

# Default policy
block in all
block out all

# Anti-spoofing
antispoof quick for { lo0 $ext_if }

# Allow loopback
pass quick on lo0 all

# Protection mechanisms
block in quick from <blacklist>
block in quick from <bruteforce>
block in quick from <ddos>

# Stateful rules with rate limiting
pass out proto tcp to any port $tcp_services flags S/SA modulate state \
    (max-src-conn 100, max-src-conn-rate 15/5, overload <ddos> flush global)
pass out proto udp to any port $udp_services keep state

# Outbound traffic
pass out inet proto icmp icmp-type { echoreq unreach } keep state
pass out proto tcp all flags S/SA modulate state
pass out proto udp all keep state
pass out proto icmp all keep state

# SSH with bruteforce protection
pass in on $ext_if proto tcp to ($ext_if) port ssh \
    flags S/SA keep state \
    (max-src-conn 10, max-src-conn-rate 3/5, \
     overload <bruteforce> flush global)

# Web services with DDoS protection
pass in on $ext_if proto tcp to ($ext_if) port { http https } \
    flags S/SA modulate state \
    (max-src-conn 100, max-src-conn-rate 15/5, \
     overload <ddos> flush global)

# Application ports
pass in on $ext_if proto tcp to ($ext_if) port { 8080 32400 8324 32469 } \
    flags S/SA modulate state
pass in on $ext_if proto udp to ($ext_if) port { 1900 5353 32410:32415 } \
    keep state

# ICMP
pass in inet proto icmp from any to ($ext_if) icmp-type { echoreq unreach } keep state
EOF

    if [[ "${CONFIG[DRY_RUN]}" == "true" ]]; then
        log INFO "[DRY RUN] Would write PF configuration:"
        echo "$pf_config"
    else
        # Write configuration
        echo "$pf_config" > "$PF_CONF" || {
            log ERROR "Failed to write PF configuration"
            return 1
        }

        # Create empty blacklist if it doesn't exist
        touch "/etc/pf.blacklist"

        # Load PF kernel module if needed
        if ! kldstat -q -m pf; then
            log INFO "Loading PF kernel module"
            kldload pf || {
                log ERROR "Failed to load PF kernel module"
                return 1
            }
            sysrc pf_load="YES" >/dev/null 2>&1
        fi

        # Enable PF in rc.conf with logging
        sysrc pf_enable="YES" pf_flags="-F all" pf_rules="$PF_CONF" >/dev/null 2>&1

        # Validate configuration
        if ! pfctl -nf "$PF_CONF"; then
            log ERROR "PF configuration validation failed"
            return 1
        fi

        # Enable and load configuration
        if ! pfctl -F all -ef "$PF_CONF"; then
            log ERROR "Failed to load PF configuration"
            return 1
        fi
    fi

    log INFO "PF firewall configuration completed"
    return 0
}

# ------------------------------------------------------------------------------
# Dotfiles Configuration Function
# ------------------------------------------------------------------------------

dotfiles_load() {
    log INFO "Starting dotfiles configuration"

    local -r HOME_DIR="/home/${CONFIG[USERNAME]}"
    local -r CONFIG_DIR="${HOME_DIR}/.config"
    local -r LOCAL_BIN="${HOME_DIR}/.local/bin"
    local -r DOTFILES_DIR="${HOME_DIR}/github/bash/dotfiles"

    # Define files to copy with source and destination
    declare -A DOTFILES=(
        ["${DOTFILES_DIR}/.bash_profile"]="${HOME_DIR}/.bash_profile"
        ["${DOTFILES_DIR}/.bashrc"]="${HOME_DIR}/.bashrc"
        ["${DOTFILES_DIR}/.profile"]="${HOME_DIR}/.profile"
        ["${DOTFILES_DIR}/.gitconfig"]="${HOME_DIR}/.gitconfig"
        ["${DOTFILES_DIR}/.tmux.conf"]="${HOME_DIR}/.tmux.conf"
        ["${DOTFILES_DIR}/Caddyfile"]="/usr/local/etc/caddy/Caddyfile"
    )

    # Define directories to copy
    declare -A CONFIG_DIRS=(
        ["${DOTFILES_DIR}/bin"]="${LOCAL_BIN}"
        ["${DOTFILES_DIR}/alacritty"]="${CONFIG_DIR}/alacritty"
        ["${DOTFILES_DIR}/tmux"]="${CONFIG_DIR}/tmux"
        ["${DOTFILES_DIR}/nvim"]="${CONFIG_DIR}/nvim"
    )

    if [[ "${CONFIG[DRY_RUN]}" != "true" ]]; then
        # Create necessary directories
        for dir in "$CONFIG_DIR" "$LOCAL_BIN" "${CONFIG_DIR}/tmux/plugins"; do
            mkdir -p "$dir" || {
                log ERROR "Failed to create directory: $dir"
                return 1
            }
        done

        # Copy dotfiles
        for src in "${!DOTFILES[@]}"; do
            local dst="${DOTFILES[$src]}"
            if [[ -f "$src" ]]; then
                mkdir -p "$(dirname "$dst")"
                if ! cp "$src" "$dst"; then
                    log ERROR "Failed to copy $src to $dst"
                    continue
                fi
                log INFO "Copied $src to $dst"
            else
                log WARN "Source file not found: $src"
            fi
        done

        # Copy configuration directories
        for src in "${!CONFIG_DIRS[@]}"; do
            local dst="${CONFIG_DIRS[$src]}"
            if [[ -d "$src" ]]; then
                mkdir -p "$dst"
                if ! cp -r "$src/." "$dst/"; then
                    log ERROR "Failed to copy directory $src to $dst"
                    continue
                fi
                log INFO "Copied directory $src to $dst"
            else
                log WARN "Source directory not found: $src"
            fi
        done

        # Set permissions
        chown -R "${CONFIG[USERNAME]}:${CONFIG[USERNAME]}" "$HOME_DIR"
        chmod 700 "$HOME_DIR"
        chmod 600 "$HOME_DIR"/.{bash_profile,bashrc,profile,gitconfig,tmux.conf}

        if [[ -f "/usr/local/etc/caddy/Caddyfile" ]]; then
            chown sawyer:sawyer "/usr/local/etc/caddy/Caddyfile"
            chmod 644 "/usr/local/etc/caddy/Caddyfile"
        fi

        # Make scripts executable
        find "$LOCAL_BIN" -type f -name "*.sh" -exec chmod +x {} \;
    fi

    log INFO "Dotfiles configuration completed"
    return 0
}

# ------------------------------------------------------------------------------
# System Information Collection Function
# ------------------------------------------------------------------------------

collect_system_info() {
    log INFO "Collecting system information"

    {
        printf "\n%s\n" "================ System Information Summary ================"
        printf "Collected on: %s\n\n" "$(date)"

        # System Information
        printf "System Information:\n"
        printf "%-20s: %s\n" "Hostname" "$(hostname)"
        printf "%-20s: %s\n" "FreeBSD Version" "$(freebsd-version)"
        printf "%-20s: %s\n" "Kernel Version" "$(uname -r)"
        printf "%-20s: %s\n" "Architecture" "$(uname -m)"

        # Hardware Information
        printf "\nHardware Information:\n"
        printf "%-20s: %s\n" "CPU Model" "$(sysctl -n hw.model)"
        printf "%-20s: %s\n" "CPU Cores" "$(sysctl -n hw.ncpu)"
        printf "%-20s: %s MB\n" "Physical Memory" "$(($(sysctl -n hw.realmem) / 1024 / 1024))"

        # Storage Information
        printf "\nStorage Information:\n"
        df -h | grep -v "devfs"

        # Network Information
        printf "\nNetwork Interfaces:\n"
        ifconfig | grep -E "^[a-z]|inet "

        # Service Status
        printf "\nActive Services:\n"
        service -e

        # Security Information
        printf "\nSecurity Information:\n"
        printf "%-20s: %s\n" "PF Status" "$(pfctl -s info 2>/dev/null | grep "Status" || echo "Disabled")"
        printf "%-20s: %s\n" "SSH Root Login" "$(grep "PermitRootLogin" /etc/ssh/sshd_config 2>/dev/null || echo "Not found")"

        # Performance Information
        printf "\nSystem Performance:\n"
        printf "%-20s: %s\n" "Load Averages" "$(uptime | awk -F': ' '{print $2}')"
        printf "%-20s\n" "Memory Usage:"
        vmstat -s | head -5 | sed 's/^/    /'

        printf "\n%s\n" "======================================================="
    } >> "${CONFIG[LOG_FILE]}"

    log INFO "System information collection completed"
}

# ------------------------------------------------------------------------------
# System Finalization Function
# ------------------------------------------------------------------------------

finalize_configuration() {
    log INFO "Starting system finalization"

    if [[ "${CONFIG[DRY_RUN]}" != "true" ]]; then
        # Update packages
        log INFO "Updating installed packages"
        if ! pkg upgrade -y; then
            log WARN "Package upgrade encountered issues"
        fi

        # Collect system information
        collect_system_info

        # Verify services
        verify_services

        # Perform security checks
        security_audit

        # Clean up temporary files
        cleanup_temp_files

        # Final system optimizations
        system_optimizations
    fi

    log INFO "System finalization completed"
    return 0
}

# ------------------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------------------

verify_services() {
    local -r CRITICAL_SERVICES=(
        "sshd"
        "pf"
        "caddy"
        "plexmediaserver"
        "chronyd"
    )

    log INFO "Verifying critical services"

    local failed_services=()
    for service in "${CRITICAL_SERVICES[@]}"; do
        if ! service "$service" status >/dev/null 2>&1; then
            failed_services+=("$service")
            log WARN "Service not running: $service"
        fi
    done

    if [[ ${#failed_services[@]} -gt 0 ]]; then
        log WARN "The following services are not running: ${failed_services[*]}"
    fi
}

security_audit() {
    log INFO "Performing security audit"

    # Check for world-writable files
    log INFO "Checking for world-writable files in sensitive directories"
    local sensitive_dirs=(
        "/usr/local/etc"
        "/usr/local/bin"
        "/usr/local/sbin"
        "/etc"
    )

    for dir in "${sensitive_dirs[@]}"; do
        find "$dir" -type f -perm -0002 2>/dev/null | while read -r file; do
            log WARN "World-writable file found: $file"
        done
    done

    # Verify SSH configuration
    if [[ -f "/etc/ssh/sshd_config" ]]; then
        log INFO "Verifying SSH configuration"
        local ssh_checks=(
            "PermitRootLogin yes"
            "PasswordAuthentication yes"
            "X11Forwarding yes"
            "PermitEmptyPasswords yes"
        )

        for check in "${ssh_checks[@]}"; do
            if grep -q "^${check}" "/etc/ssh/sshd_config"; then
                log WARN "Potentially insecure SSH setting found: ${check}"
            fi
        done
    fi

    # Check firewall status
    log INFO "Verifying firewall status"
    if ! pfctl -s info >/dev/null 2>&1; then
        log WARN "PF firewall is not running"
    fi

    # Check for unowned files
    log INFO "Checking for unowned files"
    find / -xdev -nouser -o -nogroup 2>/dev/null | while read -r file; do
        log WARN "Unowned file found: $file"
    done
}

cleanup_temp_files() {
    log INFO "Cleaning temporary files"

    # Clean package cache
    if [[ "${CONFIG[CLEAN_PKG_CACHE]}" == "true" ]]; then
        pkg clean -a -y
    fi

    # Clean temporary directories
    local -r tmp_dirs=(
        "/tmp"
        "/var/tmp"
        "/usr/local/tmp"
    )

    for dir in "${tmp_dirs[@]}"; do
        if [[ -d "$dir" ]]; then
            find "$dir" -type f -atime +7 -delete 2>/dev/null
        fi
    done

    # Clean old logs
    if [[ -d "/var/log" ]]; then
        find "/var/log" -type f -name "*.old" -delete 2>/dev/null
        find "/var/log" -type f -name "*.0" -delete 2>/dev/null
        find "/var/log" -type f -name "*.1" -delete 2>/dev/null
    fi
}

system_optimizations() {
    log INFO "Applying system optimizations"

    # Kernel optimizations
    local -A sysctl_opts=(
        ["kern.ipc.somaxconn"]="4096"
        ["kern.ipc.maxsockbuf"]="16777216"
        ["net.inet.tcp.sendspace"]="262144"
        ["net.inet.tcp.recvspace"]="262144"
        ["kern.maxfiles"]="200000"
        ["kern.maxfilesperproc"]="100000"
        ["net.inet.tcp.delayed_ack"]="0"
        ["net.inet.tcp.fastopen.server"]="1"
        ["net.inet.tcp.keepidle"]="60000"
        ["net.inet.tcp.keepintvl"]="15000"
    )

    # Apply sysctl settings
    for key in "${!sysctl_opts[@]}"; do
        if ! sysctl "${key}=${sysctl_opts[$key]}" >/dev/null 2>&1; then
            log WARN "Failed to set sysctl option: ${key}=${sysctl_opts[$key]}"
        fi
    done

    # Loader configurations for next boot
    local -A loader_opts=(
        ["kern.ipc.shmseg"]="1024"
        ["kern.ipc.shmmni"]="1024"
        ["kern.maxproc"]="10000"
        ["kern.ipc.semmni"]="1024"
        ["kern.ipc.semmns"]="2048"
        ["kern.ipc.semmnu"]="256"
    )

    # Apply loader settings
    for key in "${!loader_opts[@]}"; do
        echo "${key}=${loader_opts[$key]}" >> /boot/loader.conf
    done
}

# ------------------------------------------------------------------------------
# Main Function
# ------------------------------------------------------------------------------

main() {
    log INFO "Starting FreeBSD system configuration"

    # Define configuration steps with descriptions
    declare -A STEPS=(
        ["check_requirements"]="Verifying system requirements"
        ["backup_system"]="Creating system backup"
        ["install_pkgs"]="Installing required packages"
        ["configure_ssh_settings"]="Configuring SSH server"
        ["configure_pf"]="Setting up PF firewall"
        ["install_and_enable_plex"]="Installing Plex Media Server"
        ["install_zig"]="Installing Zig compiler"
        ["install_caddy"]="Installing Caddy web server"
        ["download_repositories"]="Downloading repositories"
        ["set_directory_permissions"]="Setting directory permissions"
        ["install_vscode_cli"]="Installing VS Code CLI"
        ["install_font"]="Installing system fonts"
        ["dotfiles_load"]="Loading dotfiles"
        ["finalize_configuration"]="Finalizing system configuration"
    )

    # Track progress
    local total_steps=${#STEPS[@]}
    local current_step=0
    local failed_steps=()
    local skipped_steps=()

    # Execute configuration steps
    for step in "${!STEPS[@]}"; do
        ((current_step++))
        local description="${STEPS[$step]}"
        log INFO "Step $current_step/$total_steps: $description"

        # Check if step should be skipped
        if [[ "${CONFIG[SKIP_STEPS]:-}" == *"$step"* ]]; then
            log INFO "Skipping step: $step"
            skipped_steps+=("$step")
            continue
        }

        # Execute step
        if ! "$step"; then
            log ERROR "Step failed: $step ($description)"
            failed_steps+=("$step")

            # Handle failure based on configuration
            case "${CONFIG[ON_FAILURE]:-abort}" in
                continue)
                    log WARN "Continuing despite failure..."
                    ;;
                retry)
                    log INFO "Retrying step: $step"
                    if ! "$step"; then
                        log ERROR "Step failed again: $step"
                        failed_steps+=("$step (retry failed)")
                    fi
                    ;;
                *)
                    log ERROR "Aborting due to step failure"
                    return 1
                    ;;
            esac
        fi
    done

    # Generate summary
    log INFO "Configuration Summary:"
    log INFO "----------------------"
    log INFO "Total steps: $total_steps"
    log INFO "Completed: $((total_steps - ${#failed_steps[@]} - ${#skipped_steps[@]}))"

    if [[ ${#skipped_steps[@]} -gt 0 ]]; then
        log INFO "Skipped steps: ${skipped_steps[*]}"
    fi

    if [[ ${#failed_steps[@]} -gt 0 ]]; then
        log WARN "Failed steps: ${failed_steps[*]}"
        return 1
    fi

    log INFO "FreeBSD system configuration completed successfully"
    log INFO "Enjoy your FreeBSD system!"
    return 0
}

# ------------------------------------------------------------------------------
# Script Initialization
# ------------------------------------------------------------------------------

# Set default configuration
: "${CONFIG[CONTINUE_ON_ERROR]:=false}"
: "${CONFIG[DRY_RUN]:=false}"
: "${CONFIG[VERBOSE]:=1}"
: "${CONFIG[LOG_FILE]:=/var/log/freebsd_setup.log}"
: "${CONFIG[USERNAME]:=sawyer}"
: "${CONFIG[CLEAN_PKG_CACHE]:=true}"
: "${CONFIG[ON_FAILURE]:=abort}"

# Script entry point
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi