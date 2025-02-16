#!/usr/bin/env bash
#
# ubuntu_setup.sh - Automated Ubuntu Setup and Hardening Script
#
# This script automates the initial configuration and hardening of an Ubuntu system.
# It performs system updates, installs essential packages, sets up users, configures
# the firewall and SSH, and deploys various additional services to streamline deployment.
#
# Usage: sudo ./ubuntu_setup.sh
#
# Note:
#   - Must be run as root.
#   - Log output is saved to /var/log/ubuntu_setup.log.
#
# Author: dunamismax | License: MIT | Version: 2.1
#

set -Eeuo pipefail

LOG_FILE="/var/log/ubuntu_setup.log"
USERNAME="sawyer"

# List of essential packages for an Ubuntu server/development environment.
PACKAGES=(
    bash
    vim
    nano
    screen
    tmux
    mc

    # Development tools and build systems
    build-essential
    cmake
    ninja-build
    meson
    gettext
    git

    # Basic server and networking
    openssh-server
    ufw
    curl
    wget
    rsync
    htop
    sudo
    bash-completion

    # Python development
    python3
    python3-dev
    python3-pip
    python3-venv

    # Essential libraries for building software
    libssl-dev
    libffi-dev
    zlib1g-dev
    libreadline-dev
    libbz2-dev
    tk-dev
    xz-utils
    libncurses5-dev
    libgdbm-dev
    libnss3-dev
    liblzma-dev
    libxml2-dev
    libxmlsec1-dev

    # System and package management utilities
    ca-certificates
    software-properties-common
    apt-transport-https
    gnupg
    lsb-release

    # Additional compilers and tools
    clang
    llvm

    # Common utilities
    netcat-openbsd
    lsof
    unzip
    zip
    
    # XFCE
    xfce4
    xfce4-goodies

    # Minimal i3-based GUI environment (for a headless/server Ubuntu)
    xorg                 # Core X server
    x11-xserver-utils    # Common X utilities
    i3-wm                # i3 window manager
    i3status             # Status bar
    i3lock               # Screen locker
    i3blocks             # Alternative status bar (optional)
    dmenu                # Program launcher
    xterm                # Basic terminal emulator
    alacritty            # Advanced terminal emulator
    feh                  # Lightweight image viewer (often used for setting wallpapers)
    fonts-dejavu-core    # Basic font set
    picom                # Compositor
)

# Nord Theme Colors (24-bit ANSI)
NORD9='\033[38;2;129;161;193m'    # Debug messages
NORD10='\033[38;2;94;129;172m'
NORD11='\033[38;2;191;97;106m'    # Error messages
NORD13='\033[38;2;235;203;139m'   # Warning messages
NORD14='\033[38;2;163;190;140m'   # Info messages
NC='\033[0m'                     # Reset to No Color

# Logging Functions
log() {
    local level="${1:-INFO}"
    shift
    local message="$*"
    local timestamp
    timestamp="$(date +"%Y-%m-%d %H:%M:%S")"
    local entry="[$timestamp] [${level^^}] $message"

    # Append log entry to file
    echo "$entry" >> "$LOG_FILE"

    # If stderr is a terminal, print with color; otherwise, print plain.
    if [ -t 2 ]; then
        case "${level^^}" in
            INFO)  printf "%b%s%b\n" "$NORD14" "$entry" "$NC" ;;
            WARN)  printf "%b%s%b\n" "$NORD13" "$entry" "$NC" ;;
            ERROR) printf "%b%s%b\n" "$NORD11" "$entry" "$NC" ;;
            DEBUG) printf "%b%s%b\n" "$NORD9"  "$entry" "$NC" ;;
            *)     printf "%s\n" "$entry" ;;
        esac
    else
        echo "$entry" >&2
    fi
}

log_info()  { log INFO "$@"; }
log_warn()  { log WARN "$@"; }
log_error() { log ERROR "$@"; }
log_debug() { log DEBUG "$@"; }

handle_error() {
    local msg="${1:-An unknown error occurred.}"
    local code="${2:-1}"
    log_error "$msg (Exit Code: $code)"
    log_error "Error encountered at line $LINENO in function ${FUNCNAME[1]:-main}."
    echo -e "${NORD11}ERROR: $msg (Exit Code: $code)${NC}" >&2
    exit "$code"
}

cleanup() {
    log_info "Performing cleanup tasks before exit."
    # Add any cleanup commands here.
}

trap cleanup EXIT
trap 'handle_error "An unexpected error occurred at line $LINENO."' ERR

# Utility Functions

print_section() {
    local title="$1"
    local border
    border=$(printf '─%.0s' {1..60})
    log_info "${NORD10}${border}${NC}"
    log_info "${NORD10}  $title${NC}"
    log_info "${NORD10}${border}${NC}"
}

check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        handle_error "Script must be run as root. Exiting."
    fi
}

check_network() {
    print_section "Network Connectivity Check"
    log_info "Verifying network connectivity..."
    if ! ping -c 1 -W 5 google.com >/dev/null 2>&1; then
        handle_error "No network connectivity. Please verify your network settings."
    fi
    log_info "Network connectivity verified."
}

update_system() {
    print_section "System Update & Upgrade"
    log_info "Updating package repositories..."
    if ! apt update -qq; then
        handle_error "Failed to update package repositories."
    fi

    log_info "Upgrading system packages..."
    if ! apt upgrade -y; then
        handle_error "Failed to upgrade packages."
    fi

    log_info "System update and upgrade complete."
}

install_packages() {
    print_section "Essential Package Installation"
    log_info "Installing packages..."
    if ! apt install -y "${PACKAGES[@]}"; then
        handle_error "Failed to install one or more packages."
    fi
    log_info "Package installation complete."
}

configure_ssh() {
    print_section "SSH Configuration"
    log_info "Configuring OpenSSH Server..."

    # Ensure OpenSSH Server is installed.
    if ! dpkg -s openssh-server &>/dev/null; then
        log_info "openssh-server is not installed. Updating repository and installing..."
        apt install -y openssh-server || handle_error "Failed to install OpenSSH Server."
        log_info "OpenSSH Server installed successfully."
    else
        log_info "OpenSSH Server already installed."
    fi

    # Enable and start the SSH service.
    systemctl enable --now ssh || handle_error "Failed to enable/start SSH service."

    # Backup the existing sshd_config file.
    local sshd_config="/etc/ssh/sshd_config"
    if [ ! -f "$sshd_config" ]; then
        handle_error "SSHD configuration file not found: $sshd_config"
    fi
    local backup
    backup="${sshd_config}.bak.$(date +%Y%m%d%H%M%S)"
    cp "$sshd_config" "$backup" || handle_error "Failed to backup $sshd_config"
    log_info "Backed up $sshd_config to $backup"

    # Define desired SSH settings.
    declare -A ssh_settings=(
        ["Port"]="22"
        ["PermitRootLogin"]="no"
        ["PasswordAuthentication"]="yes"
        ["PermitEmptyPasswords"]="no"
        ["ChallengeResponseAuthentication"]="no"
        ["Protocol"]="2"
        ["MaxAuthTries"]="5"
        ["ClientAliveInterval"]="600"
        ["ClientAliveCountMax"]="48"
    )

    # Update or add each setting in the sshd_config file.
    for key in "${!ssh_settings[@]}"; do
        if grep -qE "^${key}[[:space:]]" "$sshd_config"; then
            sed -i "s/^${key}[[:space:]].*/${key} ${ssh_settings[$key]}/" "$sshd_config"
        else
            echo "${key} ${ssh_settings[$key]}" >> "$sshd_config"
        fi
    done

    # Restart the SSH service to apply the new configuration.
    systemctl restart ssh || handle_error "Failed to restart SSH service."
    log_info "SSH configuration updated successfully."
}

configure_firewall() {
    print_section "Firewall Configuration"
    log_info "Configuring firewall with ufw..."

    local ufw_cmd="/usr/sbin/ufw"
    if [ ! -x "$ufw_cmd" ]; then
        handle_error "ufw command not found at $ufw_cmd. Please install ufw."
    fi

    "$ufw_cmd" default deny incoming || log_warn "Failed to set default deny incoming"
    "$ufw_cmd" default allow outgoing || log_warn "Failed to set default allow outgoing"
    "$ufw_cmd" allow 22/tcp || log_warn "Failed to allow SSH"
    "$ufw_cmd" allow 80/tcp || log_warn "Failed to allow HTTP"
    "$ufw_cmd" allow 443/tcp || log_warn "Failed to allow HTTPS"
    "$ufw_cmd" --force enable || handle_error "Failed to enable ufw firewall"

    systemctl enable ufw || log_warn "Failed to enable ufw service"
    systemctl start ufw || log_warn "Failed to start ufw service"
    log_info "Firewall configured and enabled."
}

caddy_config() {
    print_section "Caddy Configuration"

    log_info "Releasing occupied network ports..."
    local tcp_ports=( "8080" "80" "443" "32400" "8324" "32469" )
    local udp_ports=( "80" "443" "1900" "5353" "32410" "32411" "32412" "32413" "32414" "32415" )
    for port in "${tcp_ports[@]}"; do
        local pids
        pids=$(lsof -t -i TCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
        if [[ -n "$pids" ]]; then
            log_info "Killing processes on TCP port $port: $pids"
            kill -9 $pids || log_warn "Failed to kill processes on TCP port $port"
        fi
    done
    for port in "${udp_ports[@]}"; do
        local pids
        pids=$(lsof -t -i UDP:"$port" 2>/dev/null || true)
        if [[ -n "$pids" ]]; then
            log_info "Killing processes on UDP port $port: $pids"
            kill -9 $pids || log_warn "Failed to kill processes on UDP port $port"
        fi
    done
    log_info "Port release process completed."

    log_info "Installing dependencies for Caddy..."
    apt install -y debian-keyring debian-archive-keyring apt-transport-https curl || \
        handle_error "Failed to install dependencies for Caddy."

    log_info "Adding Caddy GPG key..."
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | \
        gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg || \
        handle_error "Failed to add Caddy GPG key."

    log_info "Adding Caddy repository..."
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | \
        tee /etc/apt/sources.list.d/caddy-stable.list || \
        handle_error "Failed to add Caddy repository."

    log_info "Updating package lists..."
    apt update || handle_error "Failed to update package lists."

    log_info "Installing Caddy..."
    apt install -y caddy || handle_error "Failed to install Caddy."
    log_info "Caddy installed successfully."

    local CUSTOM_CADDYFILE="/home/sawyer/github/linux/dotfiles/Caddyfile"
    local DEST_CADDYFILE="/etc/caddy/Caddyfile"
    if [ -f "$CUSTOM_CADDYFILE" ]; then
        log_info "Copying custom Caddyfile from $CUSTOM_CADDYFILE to $DEST_CADDYFILE..."
        cp -f "$CUSTOM_CADDYFILE" "$DEST_CADDYFILE" || log_warn "Failed to copy custom Caddyfile."
    else
        log_warn "Custom Caddyfile not found at $CUSTOM_CADDYFILE"
    fi

    log_info "Enabling Caddy service..."
    systemctl enable caddy || log_warn "Failed to enable Caddy service."

    log_info "Restarting Caddy service..."
    systemctl restart caddy || log_warn "Failed to restart Caddy service."

    log_info "Caddy configuration completed successfully."
}

setup_repos() {
    print_section "GitHub Repositories Setup"
    log_info "Setting up GitHub repositories for user '$USERNAME'..."

    local GH_DIR="/home/$USERNAME/github"

    # Create the GitHub directory if it doesn't exist.
    if ! mkdir -p "$GH_DIR"; then
        handle_error "Failed to create GitHub directory at $GH_DIR."
    fi

    # Loop through each repository and clone it.
    for repo in bash windows web python go misc; do
        local REPO_DIR="$GH_DIR/$repo"

        # Remove the repo directory if it already exists.
        if [ -d "$REPO_DIR" ]; then
            log_info "Removing existing repository directory for '$repo'..."
            rm -rf "$REPO_DIR" || log_warn "Failed to remove existing directory '$REPO_DIR'."
        fi

        log_info "Cloning repository '$repo' into '$REPO_DIR'..."
        if ! git clone "https://github.com/dunamismax/$repo.git" "$REPO_DIR"; then
            log_warn "Failed to clone repository '$repo'."
        else
            log_info "Repository '$repo' cloned successfully."
        fi
    done

    # Ensure the entire GitHub directory is owned by the target user.
    log_info "Setting ownership of '$GH_DIR' and all its contents to '$USERNAME'..."
    if ! chown -R "$USERNAME:$USERNAME" "$GH_DIR"; then
        log_warn "Failed to set ownership for '$GH_DIR'."
    else
        log_info "Ownership for '$GH_DIR' has been set to '$USERNAME'."
    fi
}

copy_shell_configs() {
    print_section "Updating Shell Configuration Files"
    local source_dir="/home/${USERNAME}/github/bash/linux/dotfiles"
    local dest_dir="/home/${USERNAME}"
    local files=(".bashrc" ".profile")

    # 1) Copy the specified dotfiles from source to destination.
    for file in "${files[@]}"; do
        local src="${source_dir}/${file}"
        local dest="${dest_dir}/${file}"
        if [ -f "$src" ]; then
            log_info "Copying ${src} to ${dest}..."
            cp -f "$src" "$dest" || log_warn "Failed to copy ${src} to ${dest}."
            chown "${USERNAME}:${USERNAME}" "$dest" || log_warn "Failed to set ownership for ${dest}."
        else
            log_warn "Source file ${src} not found; skipping."
        fi
    done

    # 2) Enable alias expansion in this script.
    shopt -s expand_aliases

    # 3) Source the new .bashrc so that aliases and functions become available now.
    #    Hard-coded to /home/sawyer/.bashrc:
    if [ -f "/home/sawyer/.bashrc" ]; then
        log_info "Sourcing /home/sawyer/.bashrc in the current script..."
        source /home/sawyer/.bashrc
    else
        log_warn "No .bashrc found at /home/sawyer/.bashrc; skipping source."
    fi

    log_info "Shell configuration files update completed (aliases/functions loaded)."
}

install_zig_binary() {
    print_section "Zig Installation"
    log_info "Installing Zig 0.12.1 for aarch64..."

    local URL="https://ziglang.org/download/0.12.1/zig-linux-aarch64-0.12.1.tar.xz"
    local INSTALL_DIR="/opt/zig"
    local TEMP_DOWNLOAD="/tmp/zig.tar.xz"

    # Ensure curl and tar are installed.
    apt install -y curl tar || handle_error "Failed to install required dependencies (curl, tar)."

    # Download the Zig tarball.
    log_info "Downloading Zig from ${URL}..."
    curl -L -o "${TEMP_DOWNLOAD}" "${URL}" || handle_error "Failed to download Zig."

    # Remove any previous installation and create the installation directory.
    rm -rf "${INSTALL_DIR}"
    mkdir -p "${INSTALL_DIR}" || handle_error "Failed to create installation directory."

    # Extract the downloaded tarball.
    log_info "Extracting Zig..."
    tar -xf "${TEMP_DOWNLOAD}" -C "${INSTALL_DIR}" --strip-components=1 || handle_error "Failed to extract Zig."

    # Create a symlink in /usr/local/bin for easy access.
    log_info "Creating symlink for Zig in /usr/local/bin..."
    ln -sf "${INSTALL_DIR}/zig" /usr/local/bin/zig || handle_error "Failed to create symlink for Zig."

    # Clean up the temporary download.
    rm -f "${TEMP_DOWNLOAD}"

    # Verify that Zig is accessible.
    if command -v zig >/dev/null 2>&1; then
        log_info "Zig installed successfully! Version: $(zig version)"
    else
        handle_error "Zig installation failed: zig not found in PATH."
    fi
}

install_ly() {
    print_section "Ly Display Manager Installation"
    log_info "Installing Ly Display Manager..."

    # 1) Verify required commands are available.
    local required_cmds=(git zig systemctl)
    for cmd in "${required_cmds[@]}"; do
        if ! command -v "$cmd" &>/dev/null; then
            handle_error "'$cmd' is not installed. Please install it and try again."
        fi
    done

    # 2) Install Ly's build dependencies for Ubuntu.
    #    Ly needs various dev libraries (pam, xcb, xkb, etc.) to build properly with Zig.
    log_info "Installing Ly build dependencies for Ubuntu..."
    if ! apt update; then
        handle_error "Failed to update package lists before installing dependencies."
    fi
    if ! apt install -y \
        build-essential \
        libpam0g-dev \
        libxcb-xkb-dev \
        libxcb-randr0-dev \
        libxcb-xinerama0-dev \
        libxcb-xrm-dev \
        libxkbcommon-dev \
        libxkbcommon-x11-dev
    then
        handle_error "Failed to install Ly build dependencies."
    fi

    # 3) Clone or update the Ly repository.
    local LY_DIR="/opt/ly"
    if [ ! -d "$LY_DIR" ]; then
        log_info "Cloning Ly repository into $LY_DIR..."
        if ! git clone https://github.com/fairyglade/ly "$LY_DIR"; then
            handle_error "Failed to clone the Ly repository."
        fi
    else
        log_info "Ly repository already exists in $LY_DIR. Updating..."
        cd "$LY_DIR" || handle_error "Failed to change directory to $LY_DIR."
        if ! git pull; then
            handle_error "Failed to update the Ly repository."
        fi
    fi

    # 4) Compile Ly using Zig.
    cd "$LY_DIR" || handle_error "Failed to change directory to $LY_DIR."
    log_info "Compiling Ly with Zig..."
    if ! zig build; then
        handle_error "Compilation of Ly failed."
    fi

    # 5) Install Ly's systemd service.
    log_info "Installing Ly systemd service..."
    if ! zig build installsystemd; then
        handle_error "Installation of Ly systemd service failed."
    fi

    # 6) Disable any conflicting display managers.
    log_info "Disabling existing display managers (gdm, sddm, lightdm, lxdm)..."
    local dm_list=(gdm sddm lightdm lxdm)
    for dm in "${dm_list[@]}"; do
        if systemctl is-enabled "${dm}.service" &>/dev/null; then
            log_info "Disabling ${dm}.service..."
            if ! systemctl disable --now "${dm}.service"; then
                handle_error "Failed to disable ${dm}.service."
            fi
        fi
    done

    # 7) Remove leftover display-manager symlink if it exists.
    if [ -L /etc/systemd/system/display-manager.service ]; then
        log_info "Removing leftover /etc/systemd/system/display-manager.service symlink..."
        if ! rm /etc/systemd/system/display-manager.service; then
            log_warn "Failed to remove display-manager.service symlink."
        fi
    fi

    # 8) Enable Ly to start on next boot.
    log_info "Enabling ly.service for next boot..."
    if ! systemctl enable ly.service; then
        handle_error "Failed to enable ly.service."
    fi

    # 09) Disable tty2 getty to prevent conflicts.
    log_info "Disabling getty@tty2.service..."
    if ! systemctl disable getty@tty2.service; then
        handle_error "Failed to disable getty@tty2.service."
    fi

    # 10) Inform the user of successful installation.
    log_info "Ly has been installed and configured as the default login manager."
    log_info "Ly will take effect on next reboot, or you can start it now with: systemctl start ly.service"
}

deploy_user_scripts() {
    print_section "Deploying User Scripts"
    log_info "Starting deployment of user scripts..."

    # Use the target user's home directory from the global USERNAME variable.
    local SCRIPT_SOURCE="/home/${USERNAME}/github/bash/linux/_scripts"
    local SCRIPT_TARGET="/home/${USERNAME}/bin"
    local EXPECTED_OWNER="${USERNAME}"

    # Ensure the source directory exists.
    if [ ! -d "$SCRIPT_SOURCE" ]; then
        handle_error "Source directory '$SCRIPT_SOURCE' does not exist."
    fi

    # Verify that the source directory is owned by the expected user.
    local source_owner
    source_owner=$(stat -c %U "$SCRIPT_SOURCE") || handle_error "Failed to retrieve ownership details of '$SCRIPT_SOURCE'."
    if [ "$source_owner" != "$EXPECTED_OWNER" ]; then
        handle_error "Invalid script source ownership for '$SCRIPT_SOURCE' (Owner: $source_owner). Expected: $EXPECTED_OWNER"
    fi

    # Ensure the target directory exists.
    if [ ! -d "$SCRIPT_TARGET" ]; then
        log_info "Creating target directory '$SCRIPT_TARGET'..."
        mkdir -p "$SCRIPT_TARGET" || handle_error "Failed to create target directory '$SCRIPT_TARGET'."
        chown "${USERNAME}:${USERNAME}" "$SCRIPT_TARGET" || log_warn "Failed to set ownership for '$SCRIPT_TARGET'."
    fi

    # Perform a dry-run deployment with rsync.
    log_info "Performing dry-run for script deployment..."
    if ! rsync --dry-run -ah --delete "${SCRIPT_SOURCE}/" "${SCRIPT_TARGET}/"; then
        handle_error "Dry-run failed for script deployment."
    fi

    # Execute the actual deployment.
    log_info "Deploying scripts from '$SCRIPT_SOURCE' to '$SCRIPT_TARGET'..."
    if ! rsync -ah --delete "${SCRIPT_SOURCE}/" "${SCRIPT_TARGET}/"; then
        handle_error "Script deployment failed."
    fi

    # Set executable permissions on all files in the target directory.
    log_info "Setting executable permissions on deployed scripts..."
    if ! find "${SCRIPT_TARGET}" -type f -exec chmod 755 {} \;; then
        handle_error "Failed to update script permissions in '$SCRIPT_TARGET'."
    fi

    log_info "Script deployment completed successfully."
}

configure_periodic() {
    print_section "Periodic Maintenance Setup"
    log_info "Configuring daily system maintenance tasks..."

    local CRON_FILE="/etc/cron.daily/ubuntu_maintenance"

    # Backup any existing maintenance script.
    if [ -f "$CRON_FILE" ]; then
        mv "$CRON_FILE" "${CRON_FILE}.bak.$(date +%Y%m%d%H%M%S)" && \
            log_info "Existing cron file backed up." || \
            log_warn "Failed to backup existing cron file at $CRON_FILE."
    fi

    cat <<'EOF' > "$CRON_FILE"
#!/bin/sh
# Ubuntu maintenance script (added by ubuntu_setup script)
apt update -qq && apt upgrade -y && apt autoremove -y && apt autoclean -y
EOF

    if chmod +x "$CRON_FILE"; then
        log_info "Daily maintenance script created and permissions set at $CRON_FILE."
    else
        log_warn "Failed to set execute permission on $CRON_FILE."
    fi
}

home_permissions() {
    print_section "Home Directory Permissions"
    log_info "Setting ownership of /home/$USERNAME and all its contents to $USERNAME..."

    # Recursively change ownership of /home/$USERNAME.
    if ! chown -R "$USERNAME:$USERNAME" "/home/$USERNAME"; then
        handle_error "Failed to change ownership of /home/$USERNAME."
    fi

    # Set the setgid bit on all directories so new files inherit the group.
    log_info "Setting the setgid bit on all directories in /home/$USERNAME..."
    if ! find "/home/$USERNAME" -type d -exec chmod g+s {} \;; then
        log_warn "Failed to set the setgid bit on one or more directories in /home/$USERNAME."
    fi

    # Apply default ACLs (if setfacl is available) to ensure the user has full permissions on newly created files.
    log_info "Applying default ACLs on /home/$USERNAME..."
    if command -v setfacl &>/dev/null; then
        if ! setfacl -R -d -m u:"$USERNAME":rwx "/home/$USERNAME"; then
            log_warn "Failed to apply default ACLs on /home/$USERNAME."
        fi
    else
        log_warn "setfacl not found; skipping default ACL configuration."
    fi

    log_info "Home directory permissions updated. Note: Future file ownership is determined by the process creating the file."
}

install_fastfetch() {
    print_section "Fastfetch Installation"
    local FASTFETCH_URL="https://github.com/fastfetch-cli/fastfetch/releases/download/2.36.1/fastfetch-linux-amd64.deb"
    local TEMP_DEB="/tmp/fastfetch-linux-amd64.deb"

    log_info "Downloading fastfetch from ${FASTFETCH_URL}..."
    if ! curl -L -o "$TEMP_DEB" "$FASTFETCH_URL"; then
        handle_error "Failed to download fastfetch deb file."
    fi

    log_info "Installing fastfetch..."
    if ! dpkg -i "$TEMP_DEB"; then
        log_warn "fastfetch installation encountered issues; attempting to fix dependencies..."
        if ! apt install -f -y; then
            handle_error "Failed to fix dependencies for fastfetch."
        fi
    fi

    rm -f "$TEMP_DEB"
    log_info "Fastfetch installed successfully."
}

dotfiles_load() {
    print_section "Loading Dotfiles"

    # Copy the Alacritty configuration folder.
    log_info "Copying Alacritty configuration to ~/.config/alacritty..."
    mkdir -p "/home/$USERNAME/.config/alacritty"
    if ! rsync -a --delete "/home/$USERNAME/github/bash/linux/dotfiles/alacritty/" "/home/$USERNAME/.config/alacritty/"; then
        handle_error "Failed to copy Alacritty configuration."
    fi

    # Copy the i3 configuration folder.
    log_info "Copying i3 configuration to ~/.config/i3..."
    mkdir -p "/home/$USERNAME/.config/i3"
    if ! rsync -a --delete "/home/$USERNAME/github/bash/linux/dotfiles/i3/" "/home/$USERNAME/.config/i3/"; then
        handle_error "Failed to copy i3 configuration."
    fi

    # Copy the i3blocks configuration folder.
    log_info "Copying i3blocks configuration to ~/.config/i3blocks..."
    mkdir -p "/home/$USERNAME/.config/i3blocks"
    if ! rsync -a --delete "/home/$USERNAME/github/bash/linux/dotfiles/i3blocks/" "/home/$USERNAME/.config/i3blocks/"; then
        handle_error "Failed to copy i3blocks configuration."
    fi

    # Set execute permissions on all scripts within the i3blocks/scripts directory.
    log_info "Setting execute permissions for i3blocks scripts..."
    if ! chmod -R +x "/home/$USERNAME/.config/i3blocks/scripts"; then
        log_warn "Failed to set execute permissions on i3blocks scripts."
    fi

    # Copy the picom configuration folder.
    log_info "Copying picom configuration to ~/.config/picom..."
    mkdir -p "/home/$USERNAME/.config/picom"
    if ! rsync -a --delete "/home/$USERNAME/github/bash/linux/dotfiles/picom/" "/home/$USERNAME/.config/picom/"; then
        handle_error "Failed to copy picom configuration."
    fi

    log_info "Dotfiles loaded successfully."
}

final_checks() {
    print_section "Final System Checks"
    log_info "Kernel version: $(uname -r)"
    log_info "System uptime: $(uptime -p)"
    log_info "Disk usage (root partition): $(df -h / | awk 'NR==2 {print $0}')"

    # Retrieve memory usage details.
    local mem_total mem_used mem_free
    read -r mem_total mem_used mem_free < <(free -h | awk '/^Mem:/{print $2, $3, $4}')
    log_info "Memory usage: Total: ${mem_total}, Used: ${mem_used}, Free: ${mem_free}"

    # Log CPU model.
    local cpu_model
    cpu_model=$(lscpu | grep 'Model name' | sed 's/Model name:[[:space:]]*//')
    log_info "CPU: ${cpu_model}"

    # Log active network interfaces.
    log_info "Active network interfaces:"
    ip -brief address | while read -r iface; do
         log_info "  $iface"
    done

    # Log system load averages.
    local load_avg
    load_avg=$(awk '{print $1", "$2", "$3}' /proc/loadavg)
    log_info "Load averages (1, 5, 15 min): ${load_avg}"
}

prompt_reboot() {
    print_section "Reboot Prompt"
    log_info "Setup complete."
    read -rp "Would you like to reboot now? [y/N]: " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        log_info "Rebooting system now..."
        shutdown -r now
    else
        log_info "Reboot canceled. Please remember to reboot later for all changes to take effect."
    fi
}

main() {
    # Ensure the script is executed with Bash.
    if [[ -z "${BASH_VERSION:-}" ]]; then
        echo -e "${NORD11}ERROR: Please run this script with bash.${NC}" >&2
        exit 1
    fi

    # Ensure the log directory exists and set proper permissions.
    local LOG_DIR
    LOG_DIR="$(dirname "$LOG_FILE")"
    if [ ! -d "$LOG_DIR" ]; then
        mkdir -p "$LOG_DIR" || handle_error "Failed to create log directory: $LOG_DIR"
    fi
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 600 "$LOG_FILE" || handle_error "Failed to set permissions on $LOG_FILE"

    log_info "Ubuntu setup script execution started."

    # Execute setup functions (ensure these are defined earlier in the script).
    check_root
    check_network
    update_system
    setup_repos
    copy_shell_configs
    install_packages
    configure_ssh
    configure_firewall
    caddy_config
    install_zig_binary
    deploy_user_scripts
    configure_periodic
    final_checks
    home_permissions
    dotfiles_load
    install_fastfetch
    install_ly
    prompt_reboot
}

main "$@"