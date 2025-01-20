#!/usr/local/bin/bash
# ------------------------------------------------------------------------------
# FreeBSD Automated Setup Script
# ------------------------------------------------------------------------------
# Automates fresh FreeBSD system configuration:
#  • Updates repositories, installs/upgrades essential software.
#  • Backs up and customizes key configuration files for security and performance.
#  • Sets up user "sawyer" with sudo privileges and a configured Bash environment.
#  • Enables/configures services: SSH, NTP (chrony), etc.
#  • Installs optional tools: Caddy, Plex, Python, Go, Rust, Zig, etc.
#
# Usage:
#  • Run as root or via sudo.
#  • Adjust variables (USERNAME, PACKAGES, etc.) as needed.
#  • Logs actions/errors to /var/log/freebsd_setup.log with timestamps.
#
# Error Handling:
#  • Uses 'set -euo pipefail' and an ERR trap for robust failure management.
#
# Compatibility:
#  • Tested on FreeBSD 13+. Verify on other versions.
#
# Author: dunamismax | License: MIT
# ------------------------------------------------------------------------------

set -Eeuo pipefail

# Check if script is run as root
if [[ $(id -u) -ne 0 ]]; then
  echo "This script must be run as root (e.g., sudo $0). Exiting."
  exit 1
fi

# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/freebsd_setup.log"
VERBOSE=2
USERNAME="sawyer"

# ------------------------------------------------------------------------------
# MAIN SCRIPT START
# You can add FreeBSD-specific functions below (e.g., pkg updates, config overwrites) and then
# call them in your "main" block at the end.
# ------------------------------------------------------------------------------

# Performing initial pkg update
pkg update

################################################################################
# Function: logging function
################################################################################
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
    local NC='\033[0m'  # No Color

    # Validate log level and set color
    case "${level^^}" in
        INFO)
            local color="${GREEN}"
            ;;
        WARN|WARNING)
            local color="${YELLOW}"
            level="WARN"
            ;;
        ERROR)
            local color="${RED}"
            ;;
        DEBUG)
            local color="${BLUE}"
            ;;
        *)
            local color="${NC}"
            level="INFO"
            ;;
    esac

    # Ensure the log file exists and is writable
    if [[ -z "${LOG_FILE:-}" ]]; then
        LOG_FILE="/var/log/freebsd_setup.log"
    fi
    if [[ ! -e "$LOG_FILE" ]]; then
        mkdir -p "$(dirname "$LOG_FILE")"
        touch "$LOG_FILE"
        chmod 644 "$LOG_FILE"
    fi

    # Format the log entry
    local log_entry="[$timestamp] [$level] $message"

    # Append to log file
    echo "$log_entry" >> "$LOG_FILE"

    # Output to console based on verbosity
    if [[ "$VERBOSE" -ge 2 ]]; then
        printf "${color}%s${NC}\n" "$log_entry" >&2
    elif [[ "$VERBOSE" -ge 1 && "$level" == "ERROR" ]]; then
        printf "${color}%s${NC}\n" "$log_entry" >&2
    fi
}

################################################################################
# Function: handle_error
################################################################################
handle_error() {
  log ERROR "An error occurred. Check the log for details."
}

# Trap any error and output a helpful message
trap 'log ERROR "Script failed at line $LINENO. See above for details."' ERR

# ------------------------------------------------------------------------------
# Backup Function (FreeBSD Adaptation)
# ------------------------------------------------------------------------------
backup_system() {
    pkg install -y rsync
    # Variables
    local SOURCE="/"
    local DESTINATION="/home/${USERNAME}/BACKUPS"
    local TIMESTAMP
    TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
    local BACKUP_FOLDER="$DESTINATION/backup-$TIMESTAMP"
    local RETENTION_DAYS=7
    local EXCLUDES=(
        "/proc/*" "/sys/*" "/dev/*" "/run/*" "/tmp/*" "/mnt/*" "/media/*"
        "/swapfile" "/lost+found" "/var/tmp/*" "/var/cache/*" "/var/log/*"
        "/var/lib/docker/*" "/root/.cache/*" "/home/*/.cache/*" "$DESTINATION"
    )

    local EXCLUDES_ARGS=()
    for EXCLUDE in "${EXCLUDES[@]}"; do
        EXCLUDES_ARGS+=(--exclude="$EXCLUDE")
    done

    mkdir -p "$BACKUP_FOLDER"
    log INFO "Starting system backup to $BACKUP_FOLDER"
    if rsync -aAXv "${EXCLUDES_ARGS[@]}" "$SOURCE" "$BACKUP_FOLDER"; then
        log INFO "Backup completed successfully: $BACKUP_FOLDER"
    else
        log ERROR "Error: Backup process failed."
        exit 1
    fi

    log INFO "Cleaning up old backups older than $RETENTION_DAYS days."
    if find "$DESTINATION" -type d -name "backup-*" -mtime +"$RETENTION_DAYS" -exec rm -rf {} \;; then
        log INFO "Old backups removed."
    else
        log WARN "Warning: Failed to remove some old backups."
    fi
}

################################################################################
# Function: install_pkgs
# Purpose: Installs a comprehensive set of packages for development, system
# administration, networking, and security.
################################################################################
install_pkgs() {
    log INFO "Updating pkg repositories and upgrading packages..."
    if ! pkg upgrade -y; then
        log ERROR "System upgrade failed. Exiting."
        return 1
    fi

    PACKAGES=(
    # Development tools
    gcc cmake git pkgconf openssl llvm autoconf automake libtool ninja meson gettext
    gmake valgrind doxygen ccache diffutils

    # Scripting and utilities
    bash zsh fish nano screen tmate mosh htop iftop
    tree wget curl rsync unzip zip ca_root_nss sudo less neovim mc jq pigz fzf lynx
    smartmontools neofetch screenfetch ncdu dos2unix figlet toilet ripgrep

    # Libraries for Python & C/C++ build
    libffi readline sqlite3 ncurses gdbm nss lzma libxml2

    # Networking, system admin, and hacking utilities
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

    log INFO "Installing pkg-based build dependencies and popular packages..."
    if ! pkg install -y "${PACKAGES[@]}"; then
        log ERROR "Failed to install one or more pkg-based dependencies. Exiting."
        return 1
    fi
    log INFO "All pkg-based build dependencies and recommended packages installed successfully."

    # Ensure Go is installed
    if ! pkg info go >/dev/null 2>&1; then
        log INFO "Installing Go..."
        if ! pkg install -y go; then
            log ERROR "Failed to install Go programming environment. Exiting."
            return 1
        fi
        log INFO "Go installed."
    else
        log INFO "Go is already installed."
    fi
}

################################################################################
# Function: configure_ssh_settings
# Purpose: Install and configure OpenSSH server on FreeBSD with security best practices
################################################################################
configure_ssh_settings() {
  log INFO "Installing OpenSSH Server..."

  # Install OpenSSH server if not already installed
  if ! pkg info openssh-portable >/dev/null 2>&1; then
    if ! pkg install -y openssh-portable; then
      log ERROR "Failed to install OpenSSH Server."
      return 1
    fi
    log INFO "OpenSSH Server installed."
  else
    log INFO "OpenSSH Server is already installed."
  fi

  # Enable sshd service in rc.conf if not already enabled
  if ! grep -q '^sshd_enable="YES"' /etc/rc.conf; then
    echo 'sshd_enable="YES"' >> /etc/rc.conf
    log INFO "Enabled sshd in /etc/rc.conf."
  else
    log INFO "sshd is already enabled in /etc/rc.conf."
  fi

  # Start/restart the sshd service
  service sshd restart
  if [ $? -ne 0 ]; then
    log ERROR "Failed to restart sshd service."
    return 1
  fi
  log INFO "sshd service restarted successfully."

  # Define the sshd_config path
  local sshd_config="/usr/local/etc/ssh/sshd_config"

  # Backup the existing sshd_config
  local backup_file="${sshd_config}.bak.$(date +%Y%m%d%H%M%S)"
  cp "$sshd_config" "$backup_file"
  if [ $? -ne 0 ]; then
    log ERROR "Failed to create backup of sshd_config. Exiting."
    return 1
  fi
  log INFO "Backup of sshd_config created at $backup_file."

  # Apply security best practices to sshd_config
  cat > "$sshd_config" <<EOF
Port 22
Protocol 2
MaxAuthTries 3
PermitRootLogin no
PasswordAuthentication no
ChallengeResponseAuthentication no
UsePAM no
X11Forwarding no
AllowTcpForwarding no
PermitEmptyPasswords no
ClientAliveInterval 300
ClientAliveCountMax 2
LogLevel VERBOSE
EOF

  log INFO "SSH configuration updated. Restarting sshd service..."

  service sshd restart
  if [ $? -ne 0 ]; then
    log ERROR "Failed to restart sshd after configuration change."
    return 1
  fi

  log INFO "OpenSSH Server configuration and hardening completed."
}

################################################################################
# Function: install_caddy
# Purpose: Install Caddy on FreeBSD, enable it in rc.conf, and start the service.
# Globals: None
# Arguments: None
# Returns:
#   0 - Success
#   1 - Failure
################################################################################
install_caddy() {
  log INFO "Installing Caddy..."

  # Check if Caddy is already installed
  if ! pkg info caddy >/dev/null 2>&1; then
    log INFO "Caddy is not installed. Installing via pkg..."
    if ! pkg install -y caddy; then
      log ERROR "Failed to install Caddy. Aborting."
      return 1
    fi
    log INFO "Caddy installation successful."
  else
    log INFO "Caddy is already installed."
  fi

  # Enable Caddy in rc.conf
  log INFO "Enabling Caddy service in rc.conf..."
  if ! sysrc caddy_enable="YES" >/dev/null 2>&1; then
    log ERROR "Failed to enable Caddy in rc.conf."
    return 1
  fi

  # Start the Caddy service
  log INFO "Starting Caddy service..."
  if ! service caddy start >/dev/null 2>&1; then
    log ERROR "Failed to start Caddy service."
    return 1
  fi

  log INFO "Caddy has been installed, enabled, and started successfully."
  return 0
}

################################################################################
# Function: install_and_enable_plex
# Purpose: Install Plex Media Server on FreeBSD, enable it in rc.conf, and start it.
# Globals: None
# Arguments: None
# Returns:
#   0 - Success
#   1 - Failure
################################################################################
install_and_enable_plex() {
  log INFO "Checking if Plex Media Server is already installed..."

  # Check if plexmediaserver is installed
  if pkg info plexmediaserver >/dev/null 2>&1; then
    log INFO "Plex Media Server is already installed. Skipping installation."
  else
    log INFO "Plex Media Server not found. Installing via pkg..."
    if ! pkg install -y plexmediaserver; then
      log ERROR "Failed to install Plex Media Server."
      return 1
    fi
    log INFO "Plex Media Server installation successful."
  fi

  # Enable Plex Media Server in rc.conf
  log INFO "Enabling Plex Media Server in rc.conf..."
  if ! sysrc plexmediaserver_enable="YES" >/dev/null 2>&1; then
    log ERROR "Failed to enable Plex Media Server in rc.conf."
    return 1
  fi

  # Start the Plex Media Server service
  log INFO "Starting Plex Media Server service..."
  if ! service plexmediaserver start >/dev/null 2>&1; then
    log ERROR "Failed to start Plex Media Server service."
    return 1
  fi

  log INFO "Plex Media Server has been installed, enabled, and started successfully."
  return 0
}

################################################################################
# Function: install_zig
################################################################################
install_zig() {
  set -euo pipefail
  log INFO "Starting installation of Zig..."

  if command -v zig &>/dev/null; then
    log INFO "Zig is already installed. Skipping Zig installation."
    return 0
  fi

  log INFO "Installing Zig..."
  ZIG_TARBALL="/tmp/zig.tar.xz"
  ZIG_INSTALL_DIR="/usr/local/zig"
  ZIG_URL="https://ziglang.org/builds/zig-linux-x86_64-0.14.0-dev.2847+db8ed730e.tar.xz"

  log INFO "Downloading Zig from $ZIG_URL..."
  if ! curl -L "$ZIG_URL" -o "$ZIG_TARBALL"; then
    log ERROR "Failed to download Zig."
    return 1
  fi

  log INFO "Extracting Zig tarball..."
  tar xf "$ZIG_TARBALL" -C /tmp/

  # Get the extracted directory name
  ZIG_EXTRACTED_DIR=$(tar -tf "$ZIG_TARBALL" | head -1 | cut -f1 -d"/")
  ZIG_EXTRACTED_DIR="/tmp/${ZIG_EXTRACTED_DIR}"

  if [[ ! -d "$ZIG_EXTRACTED_DIR" ]]; then
    log ERROR "Extraction failed: '$ZIG_EXTRACTED_DIR' does not exist!"
    return 1
  fi

  log INFO "Installing Zig to $ZIG_INSTALL_DIR..."
  rm -rf "$ZIG_INSTALL_DIR"
  mv "$ZIG_EXTRACTED_DIR" "$ZIG_INSTALL_DIR"

  log INFO "Creating symlink for Zig binary..."
  ln -sf "$ZIG_INSTALL_DIR/zig" /usr/local/bin/zig
  chmod +x /usr/local/bin/zig

  log INFO "Cleaning up temporary files..."
  rm -f "$ZIG_TARBALL"

  log INFO "Zig installation complete."
}

################################################################################
# Function: install_vscode_cli
################################################################################
install_vscode_cli() {
  log INFO "Creating symbolic link for Node.js..."

  if [ -e "/usr/local/node" ] || [ -L "/usr/local/node" ]; then
    rm -f "/usr/local/node"
  fi

  if ln -s "$(which node)" /usr/local/node; then
    log INFO "Symbolic link created at /usr/local/node."
  else
    log ERROR "Failed to create symbolic link for Node.js."
    return 1
  fi

  log INFO "Downloading Visual Studio Code CLI..."
  if curl -Lk 'https://code.visualstudio.com/sha/download?build=stable&os=cli-alpine-x64' --output vscode_cli.tar.gz; then
    log INFO "Downloaded vscode_cli.tar.gz successfully."
  else
    log ERROR "Failed to download vscode_cli.tar.gz."
    return 1
  fi

  log INFO "Extracting vscode_cli.tar.gz..."
  if tar -xf vscode_cli.tar.gz; then
    log INFO "Extraction completed successfully."
  else
    log ERROR "Failed to extract vscode_cli.tar.gz."
    return 1
  fi

  log INFO "Visual Studio Code CLI installation steps completed."
  log INFO "Run './code tunnel --name freebsd-server' from ~ to run the tunnel"
}

################################################################################
# Function: install_font
# Purpose: Download and install the specified font on FreeBSD.
# Globals: None
# Arguments: None
# Returns:
#   0 - Success
#   1 - Failure
################################################################################
install_font() {
  local font_url="https://github.com/ryanoasis/nerd-fonts/raw/master/patched-fonts/FiraCode/Regular/FiraCodeNerdFont-Regular.ttf"
  local font_dir="/usr/local/share/fonts/nerd-fonts"
  local font_file="FiraCodeNerdFont-Regular.ttf"

  log INFO "Starting font installation..."

  # Create the font directory if it doesn't exist
  if [ ! -d "$font_dir" ]; then
    log INFO "Creating font directory: $font_dir"
    if ! mkdir -p "$font_dir"; then
      log ERROR "Failed to create font directory: $font_dir"
      return 1
    fi
  fi

  # Download the font
  log INFO "Downloading font from $font_url"
  if ! fetch -o "$font_dir/$font_file" "$font_url"; then
    log ERROR "Failed to download font from $font_url"
    return 1
  fi

  # Refresh font cache
  log INFO "Refreshing font cache..."
  if ! fc-cache -fv >/dev/null 2>&1; then
    log ERROR "Failed to refresh font cache."
    return 1
  fi

  log INFO "Font installation completed successfully."
  return 0
}

################################################################################
# Function: download_repositories
################################################################################
download_repositories() {
  log INFO "Downloading GitHub repositories"

  local github_dir="/home/${USERNAME}/github"
  log INFO "Creating GitHub directory at $github_dir"
  mkdir -p "$github_dir"

  log INFO "Changing to GitHub directory"
  cd "$github_dir" || exit 1

  repos=(
    "bash" "c" "religion" "windows" "hugo" "python"
  )

  for repo in "${repos[@]}"; do
    if [ -d "$repo" ]; then
      log INFO "Removing existing directory: $repo"
      rm -rf "$repo"
    fi

    log INFO "Cloning repository: $repo"
    git clone "https://github.com/dunamismax/${repo}.git"
  done

  log INFO "Download completed"

  # Permissions and ownership adjustments might differ on FreeBSD;
  # adjust groups/users as appropriate for your FreeBSD setup.
  log INFO "Setting ownership and permissions for Hugo public directory"
  chown -R www:www "${github_dir}/hugo/dunamismax.com/public"
  chmod -R 755 "${github_dir}/hugo/dunamismax.com/public"

  log INFO "Setting ownership and permissions for Hugo directory"
  chown -R caddy:caddy "${github_dir}/hugo"
  chmod o+rx "/home/${USERNAME}/" "$github_dir" "${github_dir}/hugo" "${github_dir}/hugo/dunamismax.com/"

  for repo in bash c c python religion windows; do
    chown -R "${USERNAME}:${USERNAME}" "${github_dir}/${repo}"
  done

  log INFO "Update repositories and permissions completed."
  cd ~
}

# ------------------------------------------------------------------------------
# FIX DIRECTORY PERMISSIONS FUNCTION
# ------------------------------------------------------------------------------

# Configuration
GITHUB_DIR="/home/sawyer/github"
HUGO_PUBLIC_DIR="/home/sawyer/github/hugo/dunamismax.com/public"
HUGO_DIR="/home/sawyer/github/hugo"
SAWYER_HOME="/home/sawyer"
BASE_DIR="/home/sawyer/github"

# NOTE: 700 == rwx for *owner only* (no permissions for group or others)
#       600 == rw for *owner only* (no permissions for group or others)
DIR_PERMISSIONS="700"   # For .git directories
FILE_PERMISSIONS="600"  # For .git files

# ------------------------------------------------------------------------------
# FUNCTION: fix_git_permissions
# ------------------------------------------------------------------------------
fix_git_permissions() {
    local git_dir="$1"
    echo "Setting stricter permissions for $git_dir"
    # Make sure the top-level .git dir has directory permissions
    chmod "$DIR_PERMISSIONS" "$git_dir"

    # Apply to all subdirectories and files inside .git
    find "$git_dir" -type d -exec chmod "$DIR_PERMISSIONS" {} \;
    find "$git_dir" -type f -exec chmod "$FILE_PERMISSIONS" {} \;

    echo "Permissions fixed for $git_dir"
}

# ------------------------------------------------------------------------------
# MAIN FUNCTION: set_directory_permissions
# ------------------------------------------------------------------------------
set_directory_permissions() {
  # 1. Make all .sh files executable under GITHUB_DIR
  log INFO "Making all .sh files executable under $GITHUB_DIR"
  find "$GITHUB_DIR" -type f -name "*.sh" -exec chmod +x {} \;

  # 2. Set ownership for directories
  log INFO "Setting ownership for $GITHUB_DIR and $SAWYER_HOME"
  chown -R sawyer:sawyer "$GITHUB_DIR"
  chown -R sawyer:sawyer "$SAWYER_HOME"

  # 3. Set ownership and permissions for Hugo public directory
  log INFO "Setting ownership and permissions for Hugo public directory"
  chmod -R 755 "$HUGO_PUBLIC_DIR"

  # 4. Set ownership and permissions for Hugo directory and related paths
  log INFO "Setting ownership and permissions for Hugo directory"
  chown -R caddy:caddy "$HUGO_DIR"
  chmod o+rx "$SAWYER_HOME" "$GITHUB_DIR" "$HUGO_DIR" "/home/sawyer/github/hugo/dunamismax.com"
  chown -R www:www "$HUGO_PUBLIC_DIR"

  # 5. Ensure BASE_DIR exists
  if [[ ! -d "$BASE_DIR" ]]; then
      echo "Error: Base directory $BASE_DIR does not exist."
      exit 1
  fi

  log INFO "Starting permission fixes in $BASE_DIR..."

  # 6. Find and fix .git directory permissions
  while IFS= read -r -d '' git_dir; do
      fix_git_permissions "$git_dir"
  done < <(find "$BASE_DIR" -type d -name ".git" -print0)

  log INFO "Permission setting completed."
}

# ------------------------------------------------------------------------------
# Function: Comfigure PF Firewall
# ------------------------------------------------------------------------------
configure_pf() {
  log INFO "Configuring PF firewall..."

  PF_CONF="/etc/pf.conf"
  BACKUP_CONF="/etc/pf.conf.bak.$(date +%Y%m%d%H%M%S)"

  # Backup existing PF configuration
  if [ -f "$PF_CONF" ]; then
    cp "$PF_CONF" "$BACKUP_CONF" && \
    log INFO "Existing PF configuration backed up to $BACKUP_CONF."
  fi

  # Define PF rules; adjust the interface (e.g., em0, re0) accordingly
  INTERFACE="em0"  # Replace with your network interface
  cat <<EOF > "$PF_CONF"
# PF configuration generated by configure_pf script

# Define network interface
ext_if = "$INTERFACE"

# Default block policy
set block-policy drop
block all

# Allow loopback
pass quick on lo0 all

# Allow established connections
pass out quick inet proto { tcp udp } from any to any keep state

# SSH
pass in quick on \$ext_if proto tcp to (\$ext_if) port 22 keep state

# HTTP/HTTPS
pass in quick on \$ext_if proto tcp to (\$ext_if) port { 80 443 } keep state

# Custom application ports (adjust as needed)
pass in quick on \$ext_if proto tcp to (\$ext_if) port { 8080, 32400, 8324, 32469 } keep state
pass in quick on \$ext_if proto udp to (\$ext_if) port { 1900, 5353, 32410, 32411, 32412, 32413, 32414, 32415 } keep state

# Additional default allow for outbound traffic
pass out all keep state
EOF

  # Ensure PF kernel module is loaded
  if ! kldstat | grep -q pf; then
    log INFO "Loading PF kernel module..."
    kldload pf || { log ERROR "Failed to load PF kernel module."; return 1; }
    echo 'pf_load="YES"' >> /boot/loader.conf
    log INFO "PF kernel module will load on boot."
  fi

  # Enable PF in rc.conf
  if ! grep -q '^pf_enable="YES"' /etc/rc.conf; then
    echo 'pf_enable="YES"' >> /etc/rc.conf
    log INFO "Enabled PF in /etc/rc.conf."
  else
    log INFO "PF is already enabled in /etc/rc.conf."
  fi

  # Check for /dev/pf
  if [ ! -c /dev/pf ]; then
    log ERROR "/dev/pf missing. Ensure PF kernel module is loaded."
    return 1
  fi

  # Load PF configuration
  if pfctl -nf "$PF_CONF"; then
    pfctl -f "$PF_CONF"
    log INFO "PF configuration loaded successfully."
  else
    log ERROR "Failed to validate or load PF configuration."
    return 1
  fi

  # Enable PF if not already active
  if pfctl -s info | grep -q "Status: Enabled"; then
    log INFO "PF is already active."
  else
    if pfctl -e; then
      log INFO "PF enabled."
    else
      log ERROR "Failed to enable PF."
      return 1
    fi
  fi

  log INFO "PF firewall configuration complete."
}

# ------------------------------------------------------------------------------
# Function: dotfiles_load
# ------------------------------------------------------------------------------
dotfiles_load() {
  log INFO "Creating necessary directories..."
  mkdir -p /home/sawyer/.config

  log INFO "Copying dotfiles to /home/sawyer..."
  cp /home/sawyer/github/bash/dotfiles/.bash_profile        /home/sawyer/
  cp /home/sawyer/github/bash/dotfiles/.bashrc              /home/sawyer/
  cp /home/sawyer/github/bash/dotfiles/.profile             /home/sawyer/
  cp /home/sawyer/github/bash/dotfiles/Caddyfile            /usr/local/etc/Caddyfile     # Adjust path if needed

  log INFO "Copying config directories to /home/sawyer/..."
  cp -r /home/sawyer/github/bash/dotfiles/bin        /home/sawyer/.local/
  cp -r /home/sawyer/github/bash/dotfiles/alacritty  /home/sawyer/.config/

  # Ensure correct ownership if running as root
  chown -R sawyer:sawyer /home/sawyer/
  chown sawyer:sawyer /usr/local/etc/Caddyfile 2>/dev/null  # Adjust path if needed

  log INFO "Dotfiles copied successfully."
}

# ------------------------------------------------------------------------------
# Function: finalize_configuration
# ------------------------------------------------------------------------------
finalize_configuration() {
  log INFO "Finalizing system configuration..."

  cd /home/sawyer

  # Upgrade installed packages using pkg
  log INFO "Upgrading installed packages..."
  if pkg upgrade -y; then
    log INFO "Packages upgraded."
  else
    log ERROR "Package upgrade failed."
  fi
  ##############################################################################
  # Additional System Logging Information
  ##############################################################################
  log INFO "Collecting system information..."

  # Uptime
  log INFO "System Uptime: $(uptime)"

  # Disk usage for root
  log INFO "Disk Usage (root): $(df -h / | tail -1)"

  # Memory usage (FreeBSD equivalent)
  log INFO "Memory and Swap Usage:"
  vmstat -s

  # CPU information
  CPU_MODEL=$(sysctl -n hw.model 2>/dev/null || echo "Unknown")
  log INFO "CPU Model: ${CPU_MODEL}"

  # Kernel version
  log INFO "Kernel Version: $(uname -r)"

  # Network configuration
  log INFO "Network Configuration: $(ifconfig -a)"

  # End of system information collection
  log INFO "System information logged."

  log INFO "System configuration finalized."
}

# ------------------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------------------
main() {
  log INFO "--------------------------------------"
  log INFO "Starting FreeBSD Automated System Configuration Script"

  # Bash script execution order:
  backup_system
  install_pkgs
  configure_ssh_settings
  configure_pf
  install_and_enable_plex
  install_zig
  install_caddy
  download_repositories
  set_directory_permissions
  install_vscode_cli
  install_font
  dotfiles_load
  finalize_configuration

  log INFO "Configuration script finished successfully."
  log INFO "Enjoy FreeBSD!!!"
  log INFO "--------------------------------------"
}

# Entrypoint
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi