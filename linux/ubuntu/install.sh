#!/usr/bin/env bash
################################################################################
# Ubuntu Automated Setup Script
################################################################################
# Description:
#   Automates the configuration of a fresh Ubuntu system for a secure, optimized,
#   and personalized environment. Key features include:
#     • System updates, backups, and user configuration.
#     • Installation of development tools, languages, and utilities.
#     • Secure SSH and UFW firewall setup.
#     • Configuration of essential services: Chrony, Fail2ban, etc.
#     • Installation of optional tools: Caddy, Plex Media Server, VS Code CLI.
#     • Setup of GitHub repositories and dotfiles for a personalized environment.
#     • System checks, logging, and optional reboot.
#
# Usage:
#   • Run as root or with sudo.
#   • Adjust variables (e.g., USERNAME, PACKAGES) as needed.
#   • Logs actions and errors to /var/log/ubuntu_setup.log with timestamps.
#
# Error Handling:
#   • Uses 'set -Eeuo pipefail' for strict error handling.
#   • Implements a custom error handler (handle_error) for robust failure management.
#   • Logs detailed error messages with context for troubleshooting.
#
# Compatibility:
#   • Tested on Ubuntu 24.10. Verify compatibility on other versions.
#
# Features:
#   • System Updates: Initial system update and package upgrades.
#   • SSH Configuration: Secure SSH server setup with best practices.
#   • Package Installation: Installs essential and optional packages.
#   • Firewall Setup: Configures UFW with predefined rules.
#   • Security Tools: Installs and configures Fail2ban for intrusion prevention.
#   • Development Tools: Installs Python, Go, Rust, and build dependencies.
#   • Media Server: Installs and configures Plex Media Server.
#   • Web Server: Installs and configures Caddy for web hosting.
#   • Dotfiles: Copies and configures dotfiles for a personalized environment.
#   • Repository Setup: Clones GitHub repositories and sets permissions.
#   • Finalization: Performs system cleanup, updates, and logs system information.
#
# Author: dunamismax | License: MIT
# Repository: https://github.com/dunamismax/bash
################################################################################

# Enable strict error handling
set -Eeuo pipefail

# Set non-interactive frontend for apt
export DEBIAN_FRONTEND=noninteractive

################################################################################
# Configuration
################################################################################
LOG_FILE="/var/log/ubuntu_setup.log"  # Path to the log file
USERNAME="sawyer"                     # Default username to configure (change as needed)

# Define packages to install
PACKAGES=(
  bash zsh fish vim nano mc screen tmux nodejs npm ninja-build meson fonts-font-awesome intltool gettext
  build-essential cmake hugo pigz exim4 openssh-server libtool pkg-config libssl-dev rfkill fonts-ubuntu
  bzip2 libbz2-dev libffi-dev zlib1g-dev libreadline-dev libsqlite3-dev tk-dev iw fonts-hack-ttf libpolkit-agent-1-dev
  xz-utils libncurses5-dev python3 python3-dev python3-pip python3-venv libfreetype6-dev flatpak xfce4-dev-tools
  git ufw perl curl wget tcpdump rsync htop passwd bash-completion neofetch tig jq fonts-dejavu-core
  nmap tree fzf lynx which patch smartmontools ntfs-3g ubuntu-restricted-extras cups neovim libglib2.0-dev
  qemu-kvm libvirt-daemon-system libvirt-clients virtinst bridge-utils acpid policykit-1 papirus-icon-theme
  chrony fail2ban ffmpeg restic fonts-dejavu flameshot libxfce4ui-2-dev libxfce4util-dev libgtk-3-dev libpolkit-gobject-1-dev
  gnome-keyring seahorse thunar dmenu i3 i3status feh alacritty picom fonts-font-awesome
)

################################################################################
# Function: Logging
################################################################################
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")

    # Define color codes for terminal output
    local RED='\033[0;31m'
    local YELLOW='\033[0;33m'
    local GREEN='\033[0;32m'
    local BLUE='\033[0;34m'
    local NC='\033[0m'  # No Color

    # Map log levels to colors
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

    # Format the log entry
    local log_entry="[$timestamp] [$level] $message"

    # Append to log file
    echo "$log_entry" >> "$LOG_FILE"

    # Output to console
    printf "${color}%s${NC}\n" "$log_entry" >&2
}

################################################################################
# Function: Error Handling
################################################################################
handle_error() {
    local error_message="${1:-An error occurred. Check the log for details.}"
    local exit_code="${2:-1}"  # Default exit code is 1
    local timestamp
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")

    # Log the error with additional context
    log ERROR "$error_message (Exit Code: $exit_code)"
    log ERROR "Script failed at line $LINENO in function ${FUNCNAME[1]}."

    # Optionally, print the error to stderr for immediate visibility
    echo "ERROR: $error_message (Exit Code: $exit_code)" >&2
    echo "Script failed at line $LINENO in function ${FUNCNAME[1]}." >&2

    # Exit with the specified exit code
    exit "$exit_code"
}

# Trap errors and log them with context
trap 'log ERROR "Script failed in function ${FUNCNAME[0]} at line $LINENO. See above for details."' ERR

################################################################################
# Initial Checks
################################################################################

# Ensure the script is run as root
if [[ $(id -u) -ne 0 ]]; then
  handle_error "This script must be run as root (e.g., sudo $0)."
fi

# Ensure the log directory exists and is writable
LOG_DIR=$(dirname "$LOG_FILE")
if [[ ! -d "$LOG_DIR" ]]; then
  mkdir -p "$LOG_DIR" || handle_error "Failed to create log directory: $LOG_DIR"
fi
touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
chmod 600 "$LOG_FILE"  # Restrict log file access to root only

# Validate network connectivity
if ! ping -c 1 google.com &>/dev/null; then
    handle_error "No network connectivity. Please check your network settings."
fi

################################################################################
# Function: Perform initial system update and upgrade
################################################################################
initial_system_update() {
    log INFO "--------------------------------------"
    log INFO "Starting initial system update and upgrade..."

    # Update package repositories
    log INFO "Updating package repositories..."
    if ! apt update; then
        handle_error "Failed to update package repositories. Check repository configuration."
    fi
    log INFO "Package repositories updated successfully."

    # Upgrade installed packages
    log INFO "Upgrading installed packages..."
    if ! apt upgrade -y; then
        handle_error "Failed to upgrade installed packages."
    fi
    log INFO "Installed packages upgraded successfully."

    log INFO "Initial system update and upgrade completed successfully."
    log INFO "--------------------------------------"
}

################################################################################
# Function: Configure SSH and security settings
# Purpose: Install and configure OpenSSH server with best practices for security
################################################################################
configure_ssh_settings() {
    log INFO "--------------------------------------"
    log INFO "Starting SSH server configuration..."

    # Install OpenSSH server if not already installed
    if ! dpkg -l | grep -qw openssh-server; then
        log INFO "Installing OpenSSH Server..."
        if ! apt install -y openssh-server; then
            handle_error "Failed to install OpenSSH Server."
        fi
        log INFO "OpenSSH Server installed successfully."
    else
        log INFO "OpenSSH Server is already installed."
    fi

    # Enable and start SSH service
    log INFO "Enabling and starting SSH service..."
    if ! systemctl enable --now ssh; then
        handle_error "Failed to enable or start SSH service."
    fi
    log INFO "SSH service enabled and started successfully."

    # Backup sshd_config before making changes
    local sshd_config="/etc/ssh/sshd_config"
    local backup_file="${sshd_config}.bak.$(date +%Y%m%d%H%M%S)"
    log INFO "Creating backup of sshd_config at $backup_file..."
    if ! cp "$sshd_config" "$backup_file"; then
        handle_error "Failed to create backup of sshd_config."
    fi
    log INFO "Backup created successfully."

    # Define desired SSH settings for the server
    declare -A sshd_settings=(
        ["Port"]="22"
        ["MaxAuthTries"]="8"
        ["MaxSessions"]="6"
        ["PermitRootLogin"]="no"
        ["Protocol"]="2"
    )

    # Apply SSH server settings
    log INFO "Configuring SSH settings in $sshd_config..."
    for setting in "${!sshd_settings[@]}"; do
        if grep -q "^${setting} " "$sshd_config"; then
            sed -i "s/^${setting} .*/${setting} ${sshd_settings[$setting]}/" "$sshd_config"
        else
            echo "${setting} ${sshd_settings[$setting]}" >> "$sshd_config"
        fi
    done
    log INFO "SSH server configuration updated successfully."

    # Restart SSH service
    log INFO "Restarting SSH service..."
    if ! systemctl restart ssh; then
        handle_error "Failed to restart SSH service. Please check the configuration."
    fi
    log INFO "SSH service restarted successfully."

    log INFO "SSH server configuration completed successfully."
    log INFO "--------------------------------------"
}

################################################################################
# Function: Install all packages
################################################################################
bootstrap_and_install_pkgs() {
    log INFO "--------------------------------------"
    log INFO "Starting package installation process..."

    # Update package repositories and upgrade existing packages
    log INFO "Updating package repositories and upgrading packages..."
    if ! apt update; then
        handle_error "Failed to update package repositories."
    fi
    if ! apt upgrade -y; then
        handle_error "Failed to upgrade installed packages."
    fi
    log INFO "System upgrade completed successfully."

    # Install packages
    local packages_to_install=()
    for pkg in "${PACKAGES[@]}"; do
        if ! dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "install ok installed"; then
            packages_to_install+=("$pkg")
        else
            log INFO "Package '$pkg' is already installed."
        fi
    done

    if [ ${#packages_to_install[@]} -gt 0 ]; then
        log INFO "Installing packages: ${packages_to_install[*]}"
        if ! apt install -y "${packages_to_install[@]}"; then
            handle_error "Failed to install one or more packages."
        fi
        log INFO "All packages installed successfully."
    else
        log INFO "All listed packages are already installed. No action needed."
    fi

    log INFO "Package installation process completed."
    log INFO "--------------------------------------"
}

################################################################################
# Function: Configure UFW firewall
################################################################################
configure_ufw() {
    log INFO "--------------------------------------"
    log INFO "Starting UFW firewall configuration..."

    # Enable and start UFW service
    log INFO "Enabling and starting UFW service..."
    if ! systemctl enable ufw; then
        handle_error "Failed to enable UFW service."
    fi
    if ! systemctl start ufw; then
        handle_error "Failed to start UFW service."
    fi
    log INFO "UFW service enabled and started successfully."

    # Activate UFW with default rules
    log INFO "Activating UFW..."
    if ! ufw --force enable; then
        handle_error "Failed to activate UFW."
    fi
    log INFO "UFW activated successfully."

    # Configure UFW rules
    log INFO "Configuring UFW rules..."
    local ufw_rules=(
        "allow ssh"
        "allow http"
        "allow 8080/tcp"
        "allow 80/tcp"
        "allow 80/udp"
        "allow 443/tcp"
        "allow 443/udp"
        "allow 32400/tcp"
        "allow 1900/udp"
        "allow 5353/udp"
        "allow 8324/tcp"
        "allow 32410/udp"
        "allow 32411/udp"
        "allow 32412/udp"
        "allow 32413/udp"
        "allow 32414/udp"
        "allow 32415/udp"
        "allow 32469/tcp"
    )

    for rule in "${ufw_rules[@]}"; do
        if ! ufw $rule; then
            log WARN "Failed to apply UFW rule: $rule"
        else
            log INFO "Applied UFW rule: $rule"
        fi
    done

    log INFO "UFW configuration completed successfully."
    log INFO "--------------------------------------"
}

###############################################################################
# Function: Force release ports
# Purpose: Kill processes listening on specified TCP and UDP ports
###############################################################################
force_release_ports() {
    log INFO "--------------------------------------"
    log INFO "Starting port release process..."

    # Step 1: Remove Apache and autoremove unused packages
    log INFO "Removing apache2..."
    if ! apt purge -y apache2; then
        log WARN "Failed to remove apache2. Continuing..."
    fi
    if ! apt autoremove -y; then
        log WARN "Failed to autoremove unused packages. Continuing..."
    fi

    # Step 2: Install net-tools if not present
    log INFO "Installing net-tools..."
    if ! apt install -y net-tools; then
        handle_error "Failed to install net-tools."
    fi
    log INFO "net-tools installed successfully."

    # Step 3: Define ports to kill (TCP and UDP separately)
    local tcp_ports=("8080" "80" "443" "32400" "8324" "32469")
    local udp_ports=("80" "443" "1900" "5353" "32410" "32411" "32412" "32413" "32414" "32415")

    log INFO "Killing processes listening on specified ports..."

    # Kill TCP processes
    for p in "${tcp_ports[@]}"; do
        pids="$(lsof -t -i TCP:"$p" -sTCP:LISTEN 2>/dev/null || true)"
        if [ -n "$pids" ]; then
            log INFO "Killing processes on TCP port $p: $pids"
            if ! kill -9 $pids; then
                log WARN "Failed to kill processes on TCP port $p."
            fi
        fi
    done

    # Kill UDP processes
    for p in "${udp_ports[@]}"; do
        pids="$(lsof -t -i UDP:"$p" 2>/dev/null || true)"
        if [ -n "$pids" ]; then
            log INFO "Killing processes on UDP port $p: $pids"
            if ! kill -9 $pids; then
                log WARN "Failed to kill processes on UDP port $p."
            fi
        fi
    done

    log INFO "Ports have been forcibly released."
    log INFO "--------------------------------------"
}

################################################################################
# Function: Install and configure fail2ban
# Purpose: Enhance system security by installing and enabling fail2ban
################################################################################
fail2ban() {
    log INFO "--------------------------------------"
    log INFO "Starting fail2ban installation and configuration..."

    # Install fail2ban if not already installed
    if ! dpkg-query -W -f='${Status}' fail2ban 2>/dev/null | grep -q "install ok installed"; then
        log INFO "Installing fail2ban..."
        if ! apt install -y fail2ban; then
            handle_error "Failed to install fail2ban."
        fi
        log INFO "fail2ban installed successfully."

        # Enable and start fail2ban service
        log INFO "Enabling and starting fail2ban service..."
        if ! systemctl enable fail2ban; then
            handle_error "Failed to enable fail2ban service."
        fi
        if ! systemctl start fail2ban; then
            handle_error "Failed to start fail2ban service."
        fi
        log INFO "fail2ban service enabled and started successfully."
    else
        log INFO "fail2ban is already installed."
    fi

    log INFO "fail2ban installation and configuration completed successfully."
    log INFO "--------------------------------------"
}

################################################################################
# Function: Install all build dependencies
# Purpose: Install system-wide dependencies for Python, C/C++, Rust, and Go
################################################################################
install_all_build_dependencies() {
    log INFO "--------------------------------------"
    log INFO "Starting installation of all build dependencies..."

    # Step 1: Update and upgrade system packages
    log INFO "Updating apt caches and upgrading packages..."
    if ! apt update; then
        handle_error "Failed to update package repositories."
    fi
    if ! apt upgrade -y; then
        handle_error "Failed to upgrade installed packages."
    fi
    log INFO "System packages updated and upgraded successfully."

    # Step 2: Install all APT-based dependencies
    log INFO "Installing apt-based build dependencies for Python, C, C++, Rust, and Go..."
    local build_dependencies=(
        build-essential make gcc g++ clang cmake git curl wget vim tmux unzip zip
        ca-certificates software-properties-common apt-transport-https gnupg lsb-release
        jq pkg-config libssl-dev libbz2-dev libffi-dev zlib1g-dev libreadline-dev
        libsqlite3-dev tk-dev libncurses5-dev libncursesw5-dev libgdbm-dev libnss3-dev
        liblzma-dev xz-utils libxml2-dev libxmlsec1-dev gdb llvm
    )

    if ! apt install -y --no-install-recommends "${build_dependencies[@]}"; then
        handle_error "Failed to install apt-based build dependencies."
    fi
    log INFO "All apt-based build dependencies installed successfully."

    # Step 3: Install Rust toolchain
    log INFO "Installing Rust toolchain via rustup..."
    if ! curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y; then
        handle_error "Failed to install Rust toolchain."
    fi
    export PATH="$HOME/.cargo/bin:$PATH"
    log INFO "Rust toolchain installed and added to PATH."

    # Step 4: Install Go
    log INFO "Installing Go..."
    if ! apt install -y golang-go; then
        handle_error "Failed to install Go."
    fi
    log INFO "Go installed successfully."

    log INFO "All build dependencies (system, Python, C/C++, Rust, Go) installed successfully."
    log INFO "--------------------------------------"
}

################################################################################
# Function: Install Caddy
# Purpose: Install and configure the Caddy web server
################################################################################
install_caddy() {
    log INFO "--------------------------------------"
    log INFO "Starting Caddy installation..."

    # Install prerequisites
    log INFO "Installing prerequisites (ubuntu-keyring, apt-transport-https, curl)..."
    if ! apt install -y ubuntu-keyring apt-transport-https curl; then
        handle_error "Failed to install prerequisites."
    fi
    log INFO "Prerequisites installed successfully."

    # Add the official Caddy GPG key
    log INFO "Adding Caddy GPG key..."
    if ! curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --batch --yes --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg; then
        handle_error "Failed to add Caddy GPG key."
    fi
    log INFO "Caddy GPG key added successfully."

    # Add the Caddy stable repository
    log INFO "Adding Caddy stable repository..."
    if ! curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        | tee /etc/apt/sources.list.d/caddy-stable.list; then
        handle_error "Failed to add Caddy repository."
    fi
    log INFO "Caddy repository added successfully."

    # Install Caddy
    log INFO "Installing Caddy..."
    if ! apt install -y caddy; then
        handle_error "Failed to install Caddy."
    fi
    log INFO "Caddy installed successfully."

    log INFO "Caddy installation completed successfully."
    log INFO "--------------------------------------"
}

################################################################################
# Function: Install and enable Plex Media Server
# Purpose: Install Plex Media Server and configure it to start on boot
################################################################################
install_and_enable_plex() {
    log INFO "--------------------------------------"
    log INFO "Starting Plex Media Server installation..."

    # Check if Plex Media Server is already installed
    if dpkg -s plexmediaserver >/dev/null 2>&1; then
        log INFO "Plex Media Server is already installed. Skipping installation."
        return
    fi

    # Install prerequisites (curl)
    log INFO "Installing prerequisites (curl)..."
    if ! dpkg -s curl >/dev/null 2>&1; then
        if ! apt install -y curl; then
            handle_error "Failed to install curl."
        fi
    fi
    log INFO "Prerequisites installed successfully."

    # Define Plex version and download URL
    local VERSION="1.41.3.9314-a0bfb8370"
    local DEB_PACKAGE="plexmediaserver_${VERSION}_amd64.deb"
    local DEB_URL="https://downloads.plex.tv/plex-media-server-new/${VERSION}/debian/${DEB_PACKAGE}"

    # Download Plex Media Server package
    log INFO "Downloading Plex Media Server package..."
    if ! curl -LO "${DEB_URL}"; then
        handle_error "Failed to download Plex Media Server package."
    fi
    log INFO "Plex Media Server package downloaded successfully."

    # Install Plex Media Server
    log INFO "Installing Plex Media Server..."
    if ! dpkg -i "${DEB_PACKAGE}"; then
        log INFO "Resolving missing dependencies..."
        if ! apt install -f -y; then
            handle_error "Failed to resolve dependencies."
        fi
        if ! dpkg -i "${DEB_PACKAGE}"; then
            handle_error "Failed to install Plex Media Server."
        fi
    fi
    log INFO "Plex Media Server installed successfully."

    # Configure partially installed packages
    log INFO "Configuring partially installed packages..."
    if ! dpkg --configure -a; then
        log WARN "Failed to configure some packages. Continuing..."
    fi

    # Enable and start Plex Media Server service
    log INFO "Enabling and starting plexmediaserver service..."
    if ! systemctl enable plexmediaserver; then
        handle_error "Failed to enable plexmediaserver service."
    fi
    if ! systemctl start plexmediaserver; then
        handle_error "Failed to start plexmediaserver service."
    fi
    log INFO "plexmediaserver service enabled and started successfully."

    log INFO "Plex Media Server installation completed successfully."
    log INFO "To configure Plex, open a browser and navigate to:"
    log INFO "  http://127.0.0.1:32400/web"
    log INFO "--------------------------------------"
}

################################################################################
# Function: Install Visual Studio Code CLI
# Purpose: Install the Visual Studio Code CLI for remote development
################################################################################
install_vscode_cli() {
    log INFO "--------------------------------------"
    log INFO "Starting Visual Studio Code CLI installation..."

    # Create symbolic link for Node.js
    log INFO "Creating symbolic link for Node.js..."
    if [ -e "/usr/local/node" ] || [ -L "/usr/local/node" ]; then
        log INFO "Removing existing symbolic link or file at /usr/local/node..."
        if ! rm -f "/usr/local/node"; then
            handle_error "Failed to remove existing symbolic link or file."
        fi
    fi

    if ! ln -s "$(which node)" /usr/local/node; then
        handle_error "Failed to create symbolic link for Node.js."
    fi
    log INFO "Symbolic link created successfully at /usr/local/node."

    # Download Visual Studio Code CLI
    log INFO "Downloading Visual Studio Code CLI..."
    if ! curl -Lk 'https://code.visualstudio.com/sha/download?build=stable&os=cli-alpine-x64' --output vscode_cli.tar.gz; then
        handle_error "Failed to download Visual Studio Code CLI."
    fi
    log INFO "Visual Studio Code CLI downloaded successfully."

    # Extract the downloaded tarball
    log INFO "Extracting vscode_cli.tar.gz..."
    if ! tar -xf vscode_cli.tar.gz; then
        handle_error "Failed to extract vscode_cli.tar.gz."
    fi
    log INFO "Extraction completed successfully."

    # Clean up the tarball
    log INFO "Cleaning up temporary files..."
    if ! rm -f vscode_cli.tar.gz; then
        log WARN "Failed to remove vscode_cli.tar.gz. Manual cleanup may be required."
    fi

    log INFO "Visual Studio Code CLI installation completed successfully."
    log INFO "Run './code tunnel --name ubuntu-server' from the current directory to start the tunnel."
    log INFO "--------------------------------------"
}

################################################################################
# Function: Setup repositories and permissions
# Purpose: Clone GitHub repositories, set ownership, and configure permissions
################################################################################
setup_repositories_and_permissions() {
    log INFO "--------------------------------------"
    log INFO "Starting repository setup and permissions configuration..."

    # Configuration
    local GITHUB_DIR="/home/${USERNAME}/github"
    local HUGO_PUBLIC_DIR="${GITHUB_DIR}/hugo/dunamismax.com/public"
    local HUGO_DIR="${GITHUB_DIR}/hugo"
    local USER_HOME="/home/${USERNAME}"
    local BASE_DIR="$GITHUB_DIR"

    # Permissions
    local DIR_PERMISSIONS="700"  # For .git directories
    local FILE_PERMISSIONS="600" # For .git files

    # Step 1: Create GitHub directory
    log INFO "Creating GitHub directory at $GITHUB_DIR"
    if ! mkdir -p "$GITHUB_DIR"; then
        handle_error "Failed to create GitHub directory: $GITHUB_DIR"
    fi

    # Step 2: Change to GitHub directory
    log INFO "Changing to GitHub directory"
    if ! cd "$GITHUB_DIR"; then
        handle_error "Failed to change to GitHub directory: $GITHUB_DIR"
    fi

    # List of repositories to clone
    local repos=(
        "bash"
        "c"
        "religion"
        "windows"
        "hugo"
        "python"
    )

    # Step 3: Clone or update repositories
    log INFO "Cloning or updating repositories..."
    for repo in "${repos[@]}"; do
        local repo_dir="${GITHUB_DIR}/${repo}"
        local repo_url="https://github.com/dunamismax/${repo}.git"

        if [[ -d "$repo_dir" ]]; then
            log INFO "Removing existing directory: $repo"
            if ! rm -rf "$repo_dir"; then
                handle_error "Failed to remove directory: $repo_dir"
            fi
        fi

        log INFO "Cloning repository: $repo"
        if ! git clone "$repo_url" "$repo_dir"; then
            handle_error "Failed to clone repository: $repo"
        fi
    done
    log INFO "Repository cloning completed successfully."

    # Step 4: Set ownership and permissions for Hugo directories
    if [[ -d "$HUGO_PUBLIC_DIR" ]]; then
        log INFO "Setting ownership and permissions for Hugo public directory..."
        if ! chown -R www-data:www-data "$HUGO_PUBLIC_DIR"; then
            handle_error "Failed to set ownership for Hugo public directory."
        fi
        if ! chmod -R 755 "$HUGO_PUBLIC_DIR"; then
            handle_error "Failed to set permissions for Hugo public directory."
        fi
    else
        log WARN "Hugo public directory not found: $HUGO_PUBLIC_DIR"
    fi

    if [[ -d "$HUGO_DIR" ]]; then
        log INFO "Setting ownership and permissions for Hugo directory..."
        if ! chown -R caddy:caddy "$HUGO_DIR"; then
            handle_error "Failed to set ownership for Hugo directory."
        fi
        if ! chmod o+rx "$USER_HOME" "$GITHUB_DIR" "$HUGO_DIR" "${HUGO_DIR}/dunamismax.com"; then
            handle_error "Failed to set permissions for Hugo directory."
        fi
    else
        log WARN "Hugo directory not found: $HUGO_DIR"
    fi

    # Step 5: Set ownership for other repositories
    for repo in bash c python religion windows; do
        local repo_dir="${GITHUB_DIR}/${repo}"
        if [[ -d "$repo_dir" ]]; then
            log INFO "Setting ownership for repository: $repo"
            if ! chown -R "${USERNAME}:${USERNAME}" "$repo_dir"; then
                handle_error "Failed to set ownership for repository: $repo"
            fi
        else
            log WARN "Repository directory not found: $repo_dir"
        fi
    done

    # Step 6: Make all .sh files executable under GITHUB_DIR
    log INFO "Making all .sh files executable under $GITHUB_DIR"
    if ! find "$GITHUB_DIR" -type f -name "*.sh" -exec chmod +x {} +; then
        handle_error "Failed to set executable permissions for .sh files."
    fi

    # Step 7: Fix .git directory permissions
    log INFO "Fixing .git directory permissions in $BASE_DIR..."
    while IFS= read -r -d '' git_dir; do
        if [[ -d "$git_dir" ]]; then
            log INFO "Setting stricter permissions for $git_dir"
            if ! chmod "$DIR_PERMISSIONS" "$git_dir"; then
                handle_error "Failed to set permissions for $git_dir"
            fi
            if ! find "$git_dir" -type d -exec chmod "$DIR_PERMISSIONS" {} +; then
                handle_error "Failed to set directory permissions for $git_dir"
            fi
            if ! find "$git_dir" -type f -exec chmod "$FILE_PERMISSIONS" {} +; then
                handle_error "Failed to set file permissions for $git_dir"
            fi
        else
            log WARN ".git directory not found: $git_dir"
        fi
    done < <(find "$BASE_DIR" -type d -name ".git" -print0)

    log INFO "Repository setup and permissions configuration completed successfully."
    log INFO "--------------------------------------"
    cd ~ || handle_error "Failed to return to home directory."
}

# ------------------------------------------------------------------------------
# Function: Load dotfiles
# Purpose: Copy dotfiles and configuration directories to the user's home directory
# ------------------------------------------------------------------------------
dotfiles_load() {
    log INFO "--------------------------------------"
    log INFO "Starting dotfiles setup..."

    # Base paths
    local user_home="/home/${USERNAME}"
    local dotfiles_dir="${user_home}/github/bash/linux/dotfiles"
    local config_dir="${user_home}/.config"
    local local_bin_dir="${user_home}/.local/bin"

    # Verify source directories exist
    if [[ ! -d "$dotfiles_dir" ]]; then
        handle_error "Dotfiles directory not found: $dotfiles_dir"
    fi

    # Create necessary directories
    log INFO "Creating required directories..."
    if ! mkdir -p "$config_dir" "$local_bin_dir"; then
        handle_error "Failed to create config or .local/bin directories."
    fi

    # Copy dotfiles to the user's home directory
    log INFO "Copying dotfiles to $user_home..."
    local dotfiles=(
        ".bash_profile"
        ".bashrc"
        ".fehbg"
        ".profile"
    )

    for file in "${dotfiles[@]}"; do
        local src="${dotfiles_dir}/${file}"
        local dst="${user_home}/${file}"
        if [[ -f "$src" ]]; then
            if ! cp "$src" "$dst"; then
                handle_error "Failed to copy file: $src"
            fi
            log INFO "Copied file: $src -> $dst"
        else
            log WARN "Source file not found: $src"
        fi
    done

    # Copy Caddyfile to /etc/caddy
    local caddyfile_src="${dotfiles_dir}/Caddyfile"
    local caddyfile_dst="/etc/caddy/Caddyfile"
    log INFO "Copying Caddyfile to $caddyfile_dst..."
    if ! cp "$caddyfile_src" "$caddyfile_dst"; then
        handle_error "Failed to copy Caddyfile."
    fi
    log INFO "Caddyfile copied successfully."

    # Copy configuration directories
    log INFO "Copying configuration directories..."
    local config_dirs=(
        "i3"
        "i3status"
        "alacritty"
        "picom"
    )

    for dir in "${config_dirs[@]}"; do
        local src="${dotfiles_dir}/${dir}"
        local dst="${config_dir}/${dir}"
        if [[ -d "$src" ]]; then
            if ! cp -r "$src" "$dst"; then
                handle_error "Failed to copy directory: $src"
            fi
            log INFO "Copied directory: $src -> $dst"
        else
            log WARN "Source directory not found: $src"
        fi
    done

    # Copy bin directory to .local/bin
    local bin_src="${dotfiles_dir}/bin"
    local bin_dst="${local_bin_dir}"
    log INFO "Copying bin directory to $bin_dst..."
    if [[ -d "$bin_src" ]]; then
        if ! cp -r "$bin_src" "$bin_dst"; then
            handle_error "Failed to copy bin directory: $bin_src"
        fi
        log INFO "Copied bin directory: $bin_src -> $bin_dst"
    else
        log WARN "Source bin directory not found: $bin_src"
    fi

    # Set ownership and permissions
    log INFO "Setting ownership and permissions..."
    if ! chown -R "${USERNAME}:${USERNAME}" "$user_home"; then
        handle_error "Failed to set ownership for $user_home."
    fi
    if ! chown caddy:caddy "$caddyfile_dst"; then
        handle_error "Failed to set ownership for $caddyfile_dst."
    fi
    if ! chmod -R u=rwX,g=rX,o=rX "$local_bin_dir"; then
        handle_error "Failed to set permissions for $local_bin_dir."
    fi

    log INFO "Dotfiles setup completed successfully."
    log INFO "--------------------------------------"
    return 0
}

# ------------------------------------------------------------------------------
# Function: Finalize system configuration
# Purpose: Perform final system updates, cleanups, and log system information
# ------------------------------------------------------------------------------
finalize_configuration() {
    log INFO "--------------------------------------"
    log INFO "Finalizing system configuration..."

    # Change to the user's home directory
    if ! cd "/home/${USERNAME}"; then
        handle_error "Failed to change to user home directory: /home/${USERNAME}"
    fi

    # Add Flatpak remote flathub repository if not already added
    log INFO "Adding Flatpak flathub repository..."
    if flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo; then
        log INFO "Flathub repository added or already exists."
    else
        handle_error "Failed to add Flathub repository."
    fi

    # Upgrade installed packages
    log INFO "Upgrading installed packages..."
    if apt update && apt upgrade -y; then
        log INFO "Packages upgraded successfully."
    else
        handle_error "Package upgrade failed."
    fi

    # Update Flatpak applications
    log INFO "Updating Flatpak applications..."
    if flatpak update -y; then
        log INFO "Flatpak applications updated successfully."
    else
        handle_error "Failed to update Flatpak applications."
    fi

    # Refresh Snap packages (if Snap is installed)
    log INFO "Refreshing Snap packages..."
    if command -v snap &>/dev/null; then
        if snap refresh; then
            log INFO "Snap packages refreshed successfully."
        else
            handle_error "Failed to refresh Snap packages."
        fi
    else
        log INFO "Snap is not installed; skipping Snap refresh."
    fi

    # Clean up local package cache
    log INFO "Cleaning up package cache..."
    if apt clean; then
        log INFO "Package cache cleaned successfully."
    else
        handle_error "Failed to clean package cache."
    fi

    # ------------------------------------------------------------------------------
    # Additional System Logging Information
    # ------------------------------------------------------------------------------
    log INFO "--------------------------------------"
    log INFO "Collecting system information..."
    log INFO "--------------------------------------"

    # Uptime
    log INFO "--------------------------------------"
    log INFO "System Uptime: $(uptime -p)"
    log INFO "--------------------------------------"

    # Disk usage for root
    log INFO "--------------------------------------"
    log INFO "Disk Usage (root): $(df -h / | tail -1)"
    log INFO "--------------------------------------"

    # Memory usage
    log INFO "--------------------------------------"
    log INFO "Memory Usage: $(free -h | grep Mem)"
    log INFO "--------------------------------------"

    # CPU information
    local CPU_MODEL
    CPU_MODEL=$(grep 'model name' /proc/cpuinfo | uniq | awk -F': ' '{print $2}')
    log INFO "--------------------------------------"
    log INFO "CPU Model: ${CPU_MODEL:-Unknown}"
    log INFO "--------------------------------------"

    # Kernel version
    log INFO "--------------------------------------"
    log INFO "Kernel Version: $(uname -r)"
    log INFO "--------------------------------------"

    # Network configuration
    log INFO "--------------------------------------"
    log INFO "Network Configuration:"
    ip addr show
    log INFO "--------------------------------------"

    # End of system information collection
    log INFO "--------------------------------------"
    log INFO "System information logged."
    log INFO "--------------------------------------"

    log INFO "System configuration finalized successfully."
    log INFO "--------------------------------------"
}

################################################################################
# Function: Prompt for reboot
# Purpose: Ask the user if they want to reboot the system
################################################################################
prompt_reboot() {
    log INFO "Setup complete. A reboot is recommended to apply all changes."
    read -p "Reboot now? (y/n): " REBOOT
    if [[ "$REBOOT" == "y" || "$REBOOT" == "Y" ]]; then
        log INFO "Rebooting the system..."
        reboot
    else
        log INFO "Reboot skipped. Please reboot manually when convenient."
    fi
}

################################################################################
# MAIN
################################################################################
main() {
    log INFO "--------------------------------------"
    log INFO "Starting Ubuntu Automated System Configuration Script"

    # Bash script execution order
    local functions=(
        initial_system_update
        configure_ssh_settings
        bootstrap_and_install_pkgs
        configure_ufw
        fail2ban
        install_all_build_dependencies
        install_and_enable_plex
        install_vscode_cli
        install_caddy
        setup_repositories_and_permissions
        dotfiles_load
        finalize_configuration
    )

    # Execute each function in order
    for func in "${functions[@]}"; do
        log INFO "Running function: $func"
        if ! $func; then
            handle_error "Function $func failed."
        fi
    done

    log INFO "Configuration script finished successfully."
    log INFO "Enjoy Ubuntu!"
    log INFO "--------------------------------------"
}

# Entrypoint
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    # Run the main function
    main "$@"

    # Prompt for reboot after successful completion
    prompt_reboot
fi