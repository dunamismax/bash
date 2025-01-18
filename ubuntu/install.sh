#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Ubuntu Automated Setup Script
# ------------------------------------------------------------------------------
# Automates fresh system configuration:
#  • Updates repositories, installs/upgrades essential software.
#  • Backs up and customizes key configuration files for security and performance.
#  • Sets up user "sawyer" with sudo privileges and a configured Bash environment.
#  • Enables/configures services: UFW, SSH, Chrony, etc.
#  • Installs optional tools: Caddy, Plex, Python, Go, Rust, Zig, etc.
#
# Usage:
#  • Run as root or via sudo.
#  • Adjust variables (USERNAME, PACKAGES, etc.) as needed.
#  • Logs actions/errors to /var/log/ubuntu_setup.log with timestamps.
#
# Error Handling:
#  • Uses 'set -euo pipefail' and an ERR trap for robust failure management.
#
# Compatibility:
#  • Tested on Ubuntu 24.10. Verify on other versions.
#
# Author: dunamismax | License: MIT
# ------------------------------------------------------------------------------

set -Eeuo pipefail
export DEBIAN_FRONTEND=noninteractive

# Check if script is run as root
if [[ $(id -u) -ne 0 ]]; then
  echo "This script must be run as root (e.g., sudo $0). Exiting."
  exit 1
fi

# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/ubuntu_setup.log"
VERBOSE=2
USERNAME="sawyer"

PACKAGES=(
  bash zsh fish vim nano mc screen tmux nodejs npm ninja-build meson fonts-font-awesome intltool gettext
  build-essential cmake hugo pigz exim4 openssh-server libtool pkg-config libssl-dev rfkill fonts-ubuntu
  bzip2 libbz2-dev libffi-dev zlib1g-dev libreadline-dev libsqlite3-dev tk-dev iw fonts-hack-ttf libpolkit-agent-1-dev
  xz-utils libncurses5-dev python3 python3-dev python3-pip python3-venv libfreetype6-dev flatpak xfce4-dev-tools
  git ufw perl curl wget tcpdump rsync htop passwd bash-completion neofetch tig jq fonts-dejavu-core
  nmap tree fzf lynx which patch smartmontools ntfs-3g ubuntu-restricted-extras cups neovim libglib2.0-dev
  qemu-kvm libvirt-daemon-system libvirt-clients virtinst bridge-utils acpid policykit-1 papirus-icon-theme
  chrony fail2ban ffmpeg restic fonts-dejavu flameshot libxfce4ui-2-dev libxfce4util-dev libgtk-3-dev libpolkit-gobject-1-dev
  gnome-keyring seahorse
)

# ------------------------------------------------------------------------------
# MAIN SCRIPT START
# You can add functions below (e.g., apt updates, config overwrites) and then
# call them in your "main" block at the end.
# ------------------------------------------------------------------------------

# Performing initial apt update
apt update

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
        LOG_FILE="/var/log/example_script.log"
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
# Backup Function
# ------------------------------------------------------------------------------
backup_system() {
    apt install -y rsync
    # Variables
    local SOURCE="/"                       # Source directory for backup
    local DESTINATION="/home/sawyer/BACKUPS" # Destination for backups
    local TIMESTAMP
    TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S") # Timestamp for folder naming
    local BACKUP_FOLDER="$DESTINATION/backup-$TIMESTAMP" # Custom dated folder
    local RETENTION_DAYS=7                 # Retain backups for 7 days
    # Exclusions for the backup
    local EXCLUDES=(
        "/proc/*"
        "/sys/*"
        "/dev/*"
        "/run/*"
        "/tmp/*"
        "/mnt/*"
        "/media/*"
        "/swapfile"
        "/lost+found"
        "/var/tmp/*"
        "/var/cache/*"
        "/var/log/*"
        "/var/lib/lxcfs/*"
        "/var/lib/docker/*"
        "/root/.cache/*"
        "/home/*/.cache/*"
        "/var/lib/plexmediaserver/*"
        "$DESTINATION"
    )
    # Create exclusion string for rsync
    local EXCLUDES_ARGS=()
    for EXCLUDE in "${EXCLUDES[@]}"; do
        EXCLUDES_ARGS+=(--exclude="$EXCLUDE")
    done
    # Ensure the destination folder exists
    mkdir -p "$BACKUP_FOLDER"
    # Perform backup using rsync
    log INFO "Starting system backup to $BACKUP_FOLDER"
    if rsync -aAXv "${EXCLUDES_ARGS[@]}" "$SOURCE" "$BACKUP_FOLDER"; then
        log INFO "Backup completed successfully: $BACKUP_FOLDER"
    else
        log ERROR "Error: Backup process failed."
        exit 1
    fi
    # Remove old backups
    log INFO "Cleaning up old backups older than $RETENTION_DAYS days."
    if find "$DESTINATION" -type d -name "backup-*" -mtime +"$RETENTION_DAYS" -exec rm -rf {} \;; then
        log INFO "Old backups removed."
    else
        log WARN "Warning: Failed to remove some old backups."
    fi
}

################################################################################
# Function: Configure SSH and security settings
# Purpose: Install and configure OpenSSH server with best practices for security
################################################################################
configure_ssh_settings() {
  log INFO "Installing OpenSSH Server..."

  # Install OpenSSH server if not already installed
  if ! dpkg -l | grep -qw openssh-server; then
    apt install -y openssh-server
    log INFO "OpenSSH Server installed."
  else
    log INFO "OpenSSH Server is already installed."
  fi

  # Enable and start SSH service
  systemctl enable --now ssh
  log INFO "ssh service enabled and started."

  log INFO "Configuring SSH settings in /etc/ssh/sshd_config..."

  # Backup sshd_config before making changes
  local sshd_config="/etc/ssh/sshd_config"
  local backup_file="${sshd_config}.bak.$(date +%Y%m%d%H%M%S)"
  cp "$sshd_config" "$backup_file" && log INFO "Backup created at $backup_file."

  # Define desired SSH settings for the server
  declare -A sshd_settings=(
    ["Port"]="22"
    ["MaxAuthTries"]="8"
    ["MaxSessions"]="6"
    ["PermitRootLogin"]="no"
    ["Protocol"]="2"
  )

  # Apply SSH server settings
  for setting in "${!sshd_settings[@]}"; do
    if grep -q "^${setting} " "$sshd_config"; then
      sed -i "s/^${setting} .*/${setting} ${sshd_settings[$setting]}/" "$sshd_config"
    else
      echo "${setting} ${sshd_settings[$setting]}" >> "$sshd_config"
    fi
  done

  log INFO "SSH server configuration updated. Restarting SSH service..."

  # Restart SSH service and handle errors
  if systemctl restart sshd; then
    log INFO "sshd service restarted successfully."
  else
    log ERROR "Failed to restart sshd service. Please check the configuration."
    return 1
  fi
}

################################################################################
# Function: bootstrap_and_install_pkgs
################################################################################
bootstrap_and_install_pkgs() {
  log INFO "Updating apt package list and upgrading existing packages..."
  apt upgrade -y

  local packages_to_install=()
  for pkg in "${PACKAGES[@]}"; do
    # If not installed, queue it up for installation
    if ! dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "install ok installed"; then
      packages_to_install+=("$pkg")
    else
      log INFO "Package '$pkg' is already installed."
    fi
  done

  if [ ${#packages_to_install[@]} -gt 0 ]; then
    log INFO "Installing packages: ${packages_to_install[*]}"
    apt install -y "${packages_to_install[@]}"
  else
    log INFO "All listed packages are already installed. No action needed."
  fi

  log INFO "Package installation process completed."
}

###############################################################################
# Enable and configure ufw.
###############################################################################
configure_ufw() {
  log INFO "Enabling ufw systemd service..."
  # Ensure ufw starts on boot, then start it now
  systemctl enable ufw
  systemctl start ufw

  log INFO "Activating ufw (will allow pre-configured rules)..."
  # --force ensures it doesn’t prompt for confirmation
  ufw --force enable

  log INFO "Configuring ufw rules..."
  ufw allow ssh
  ufw allow http
  ufw allow 8080/tcp
  ufw allow 80/tcp
  ufw allow 80/udp
  ufw allow 443/tcp
  ufw allow 443/udp
  ufw allow 32400/tcp
  ufw allow 1900/udp
  ufw allow 5353/udp
  ufw allow 8324/tcp
  ufw allow 32410/udp
  ufw allow 32411/udp
  ufw allow 32412/udp
  ufw allow 32413/udp
  ufw allow 32414/udp
  ufw allow 32415/udp
  ufw allow 32469/tcp

  log INFO "UFW configuration complete."
}

###############################################################################
# Function: force_release_ports
###############################################################################
force_release_ports() {
  # Step 1: Remove Apache, then autoremove
  log INFO "Removing apache2..."
  apt purge -y apache2

  # Step 2: Install net-tools if not present
  log INFO "Installing net-tools..."
  apt install -y net-tools

  # Step 3: Define ports to kill (TCP and UDP separately)
  local tcp_ports=("8080" "80" "443" "32400" "8324" "32469")
  local udp_ports=("80" "443" "1900" "5353" "32410" "32411" "32412" "32413" "32414" "32415")

  log INFO "Killing any processes listening on the specified ports..."

  # Kill TCP processes
  for p in "${tcp_ports[@]}"; do
    # lsof -t: print only the process IDs
    # -i TCP:$p: match TCP port
    # -sTCP:LISTEN: only processes in LISTEN state
    pids="$(lsof -t -i TCP:"$p" -sTCP:LISTEN 2>/dev/null || true)"
    if [ -n "$pids" ]; then
      echo "Killing processes on TCP port $p: $pids"
      kill -9 $pids
    fi
  done

  # Kill UDP processes
  for p in "${udp_ports[@]}"; do
    # -i UDP:$p: match UDP port
    pids="$(lsof -t -i UDP:"$p" 2>/dev/null || true)"
    if [ -n "$pids" ]; then
      log INFO "Killing processes on UDP port $p: $pids"
      kill -9 $pids
    fi
  done

  log INFO "Ports have been forcibly released."
}

################################################################################
# Function: configure_timezone
################################################################################
configure_timezone() {
  local tz="${1:-UTC}"  # Default to UTC if not specified
  log INFO "Configuring timezone to '${tz}'..."

  # Ensure tzdata is present (usually installed by default, but just in case)
  apt install -y tzdata

  # Timedatectl sets both system clock and hardware clock
  timedatectl set-timezone "$tz"

  log INFO "Timezone set to $tz."
}

################################################################################
# Function: fail2ban
################################################################################
fail2ban() {
  log INFO "Installing fail2ban..."

  # 1) Install fail2ban (from ubuntu repositories)
  if ! dpkg-query -W -f='${Status}' fail2ban 2>/dev/null | grep -q "install ok installed"; then
    log INFO "Installing fail2ban..."
    apt install -y fail2ban
    systemctl enable fail2ban
    systemctl start fail2ban
  else
    log INFO "fail2ban is already installed."
  fi

  log INFO "Security hardening steps completed."
}

################################################################################
# Function: configure_ntp
################################################################################
configure_ntp() {
  log INFO "Configuring NTP (chrony)..."

  # 1) Install chrony if it is not already installed
  if ! dpkg-query -W -f='${Status}' chrony 2>/dev/null | grep -q "install ok installed"; then
    log INFO "Installing chrony..."
    apt install -y chrony
  else
    log INFO "chrony is already installed."
  fi

  # 2) Enable and start chrony
  systemctl enable chrony
  systemctl restart chrony

  log INFO "NTP (chrony) configuration complete."
}

################################################################################
# Combined Function: Installs APT dependencies for Python & C/C++ build, Rust,
# and Go, plus basic system updates, core packages, etc.
################################################################################
install_all_build_dependencies() {
    # 1) Update and upgrade system packages
    log INFO "Updating apt caches and upgrading packages..."
    apt upgrade -y

    # 2) Install all APT-based dependencies in one shot
    log INFO "Installing apt-based build dependencies for Python, C, C++, Rust, and Go..."
      if ! apt install -y --no-install-recommends \
        build-essential \
        make \
        gcc \
        g++ \
        clang \
        cmake \
        git \
        curl \
        wget \
        vim \
        tmux \
        unzip \
        zip \
        ca-certificates \
        software-properties-common \
        apt-transport-https \
        gnupg \
        lsb-release \
        jq \
        pkg-config \
        libssl-dev \
        libbz2-dev \
        libffi-dev \
        zlib1g-dev \
        libreadline-dev \
        libsqlite3-dev \
        tk-dev \
        libncurses5-dev \
        libncursesw5-dev \
        libgdbm-dev \
        libnss3-dev \
        liblzma-dev \
        xz-utils \
        libxml2-dev \
        libxmlsec1-dev \
        gdb \
        llvm
    then
        log ERROR "Failed to install all apt-based dependencies. Exiting."
        return 1
    fi

    log INFO "All apt-based build dependencies installed successfully."

    # 3) Install Rust toolchain
    log INFO "Installing Rust toolchain via rustup..."
    if ! curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y; then
        log ERROR "Failed to install Rust toolchain. Exiting."
        return 1
    fi

    # Make Rust available in the current session
    export PATH="$HOME/.cargo/bin:$PATH"
    log INFO "Rust toolchain installed and added to PATH."

    # 4) Install Go
    log INFO "Installing Go..."
    if ! apt install -y golang-go; then
        log ERROR "Failed to install Go programming environment. Exiting."
        return 1
    fi

    log INFO "Go installed."

    # 5) Final message
    log INFO "All dependencies (system, Python, C/C++, Rust, Go) installed successfully."
}

################################################################################
# Function: install_caddy
################################################################################
install_caddy() {
  log INFO "Installing and enabling Caddy..."

  apt install -y ubuntu-keyring apt-transport-https curl

  # Add the official Caddy GPG key
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --batch --yes --dearmor \
         -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg

  # Add the Caddy stable repository
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | tee /etc/apt/sources.list.d/caddy-stable.list

  apt install -y caddy

  log INFO "Caddy installed."
}

################################################################################
# Function: install_and_enable_plex
################################################################################
install_and_enable_plex() {
  set -e  # Exit immediately if a command exits with a non-zero status

  log INFO "Checking if Plex Media Server is already installed..."
  if dpkg -s plexmediaserver >/dev/null 2>&1; then
    log INFO "Plex Media Server is already installed. Skipping installation."
    return
  fi

  log INFO "Installing prerequisites (curl) if not already installed..."
  if ! dpkg -s curl >/dev/null 2>&1; then
    apt install -y curl
  fi

  # Change this to match the latest Plex version you want to install
  local VERSION="1.41.3.9314-a0bfb8370"
  local DEB_PACKAGE="plexmediaserver_${VERSION}_amd64.deb"
  local DEB_URL="https://downloads.plex.tv/plex-media-server-new/${VERSION}/debian/${DEB_PACKAGE}"

  log INFO "Downloading Plex Media Server package from Plex..."
  curl -LO "${DEB_URL}"

  log INFO "Installing Plex Media Server..."
  if ! dpkg -i "${DEB_PACKAGE}"; then
    log INFO "Resolving missing dependencies..."
    apt install -f -y
    dpkg -i "${DEB_PACKAGE}"
  fi

  log INFO "Configuring any partially installed packages..."
  dpkg --configure -a

  log INFO "Enabling and starting plexmediaserver service..."
  systemctl enable plexmediaserver
  systemctl start plexmediaserver

  log INFO "Plex Media Server installation complete!"
  log INFO "To configure Plex, open a browser on the same machine and go to:"
  log INFO "  http://127.0.0.1:32400/web"
}

# ------------------------------------------------------------------------------
# Function: install zig
# ------------------------------------------------------------------------------
install_zig() {
  set -euo pipefail
  log INFO "Starting installation of Zig..."

  # ------------------------
  # 1. Check for Zig
  # ------------------------
  if command -v zig &>/dev/null; then
    log INFO "Zig is already installed. Skipping Zig installation."
    return 0
  fi

  # ------------------------
  # 2. Install Zig
  # ------------------------
  log INFO "Installing Zig..."
  ZIG_VERSION="zig-linux-x86_64-0.14.0-dev.2643+fb43e91b2"
  ZIG_URL="https://ziglang.org/builds/${ZIG_VERSION}.tar.xz"
  ZIG_TARBALL="/tmp/${ZIG_VERSION}.tar.xz"
  ZIG_EXTRACTED_DIR="/tmp/${ZIG_VERSION}"
  ZIG_INSTALL_DIR="/usr/local/zig"

  log INFO "Downloading Zig from $ZIG_URL..."
  wget -O "$ZIG_TARBALL" "$ZIG_URL"

  log INFO "Extracting Zig tarball..."
  tar xf "$ZIG_TARBALL" -C /tmp/

  if [[ ! -d "$ZIG_EXTRACTED_DIR" ]]; then
    log ERROR "Extraction failed: '$ZIG_EXTRACTED_DIR' does not exist!"
    exit 1
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
# Function: Installs vscode cli
################################################################################
install_vscode_cli() {
  log INFO "Creating symbolic link for Node.js..."

  # If /usr/local/node already exists (as a file, directory, or symlink), remove it.
  if [ -e "/usr/local/node" ] || [ -L "/usr/local/node" ]; then
    rm -f "/usr/local/node"
  fi

  # Create the symbolic link
  if ln -s "$(which node)" /usr/local/node; then
    log INFO "Symbolic link created at /usr/local/node."
  else
    log ERROR "Failed to create symbolic link for Node.js."
    return 1
  fi

  # Download the Visual Studio Code CLI for Alpine Linux
  log INFO "Downloading Visual Studio Code CLI..."
  if curl -Lk 'https://code.visualstudio.com/sha/download?build=stable&os=cli-alpine-x64' --output vscode_cli.tar.gz; then
    log INFO "Downloaded vscode_cli.tar.gz successfully."
  else
    log ERROR "Failed to download vscode_cli.tar.gz."
    return 1
  fi

  # Extract the downloaded tarball
  log INFO "Extracting vscode_cli.tar.gz..."
  if tar -xf vscode_cli.tar.gz; then
    log INFO "Extraction completed successfully."
  else
    log ERROR "Failed to extract vscode_cli.tar.gz."
    return 1
  fi

  log INFO "Visual Studio Code CLI installation steps completed."
  log INFO "Run './code tunnel --name ubuntu-server' from ~ to run the tunnel"
}

# ------------------------------------------------------------------------------
# Function: Installs JetBrains Mono font via package manager
# ------------------------------------------------------------------------------
install_jetbrainsmono() {
  log INFO "Starting JetBrains Mono installation via apt..."

  if apt-get install -y fonts-jetbrains-mono; then
    log INFO "JetBrains Mono fonts installed successfully."
  else
    log ERROR "Failed to install JetBrains Mono fonts."
    return 1
  fi
}

# ------------------------------------------------------------------------------
# Function: Installs PipeWire, removes PulseAudio, and enables PipeWire user services globally
# ------------------------------------------------------------------------------
switch_to_pipewire() {
  log INFO "Installing PipeWire and setting it to default."

  log INFO "1. Remove PulseAudio."
  apt remove --purge -y pulseaudio

  log INFO "2. Update repositories and install PipeWire-related packages."
  apt update
  apt install -y pipewire pipewire-pulse pipewire-alsa wireplumber

  log INFO "3. Enable PipeWire user services globally."
  # This means any user who logs in will have these services started in their session.
  systemctl --global enable pipewire.service pipewire-pulse.service wireplumber.service

  # Optionally, mask PulseAudio’s user services so they can’t be started again:
  # systemctl --global mask pulseaudio.service pulseaudio.socket

  log INFO "PipeWire user services have been globally enabled."
  log INFO "They will start automatically for each user at login."
}

# ------------------------------------------------------------------------------
# Function: Installs i3, xfce, and required GUI components
# ------------------------------------------------------------------------------
install_gui() {
  export DEBIAN_FRONTEND=noninteractive

  log INFO "Updating package lists..."
  apt-get update

  # Install Xorg and lightdm
  log INFO "Installing Xorg, lightdm, and essential GUI packages..."
  apt-get install -y xorg lightdm

  # Set LightDM as the default display manager
  log INFO "Configuring LightDM as the default display manager..."
  debconf-set-selections <<< "lightdm shared/default-x-display-manager select lightdm"
  systemctl enable lightdm

  # Install i3 window manager and its common addons
  log INFO "Installing i3 window manager and addons..."
  apt-get install -y i3 i3blocks i3lock rofi feh polybar fonts-powerline fonts-noto \
    xterm alacritty ranger pavucontrol alsa-utils picom libxcb1-dev libxcb-keysyms1-dev \
    libpango1.0-dev libxcb-util0-dev libxcb-icccm4-dev libyajl-dev libstartup-notification0-dev \
    libxcb-randr0-dev libev-dev libxcb-cursor-dev libxcb-xinerama0-dev libxcb-xkb-dev libxkbcommon-dev \
    libxkbcommon-x11-dev autoconf xutils-dev libtool automake libxcb-xrm-dev

  # Install xfce and its common addons
  log INFO "Installing xfce and addons..."
  apt-get install -y xfce4 xfce4-goodies xfce4-session xfce4-power-manager thunar thunar-volman gvfs-backends \
    lightdm lightdm-gtk-greeter xfce4-settings xfce4-terminal xfce4-notifyd xfce4-screenshooter \
    xfce4-taskmanager ristretto mousepad parole pipewire pavucontrol arc-theme adwaita-icon-theme
}

################################################################################
# Function: download_repositories
################################################################################
download_repositories() {
  log INFO "Downloading github repositories"

  log INFO "Creating github directory"
  mkdir -p /home/sawyer/github

  log INFO "Changing to github directory"
  cd /home/sawyer/github || exit 1

  # List of repositories to clone (folder name plus GitHub path)
  # If the local folder name matches the repo name, it's easy:
  repos=(
    "bash"
    "c"
    "religion"
    "windows"
    "hugo"
    "python"
  )

  # Loop over each repo, remove the folder if it exists, then clone fresh
  for repo in "${repos[@]}"; do
    if [ -d "$repo" ]; then
      log INFO "Removing existing directory: $repo"
      rm -rf "$repo"
    fi

    log INFO "Cloning repository: $repo"
    git clone "https://github.com/dunamismax/${repo}.git"
  done

  log INFO "Download completed"

  # Set permissions and ownership for the Hugo directory
  log INFO "Setting ownership and permissions for Hugo public directory"
  chown -R www-data:www-data "/home/sawyer/github/hugo/dunamismax.com/public"
  chmod -R 755 "/home/sawyer/github/hugo/dunamismax.com/public"

  log INFO "Setting ownership and permissions for Hugo directory"
  chown -R caddy:caddy "/home/sawyer/github/hugo"
  chmod o+rx "/home/sawyer/" "/home/sawyer/github/" "/home/sawyer/github/hugo/" "/home/sawyer/github/hugo/dunamismax.com/"

  # Set permissions and ownership for github directory
  chown -R sawyer:sawyer "/home/sawyer/github/bash"
  chown -R sawyer:sawyer "/home/sawyer/github/c"
  chown -R sawyer:sawyer "/home/sawyer/github/python"
  chown -R sawyer:sawyer "/home/sawyer/github/religion"
  chown -R sawyer:sawyer "/home/sawyer/github/windows"

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
  log INFO "Setting ownership for /home/sawyer/github and /home/sawyer"
  chown -R sawyer:sawyer /home/sawyer/github
  chown -R sawyer:sawyer /home/sawyer/

  # 3. Set ownership and permissions for Hugo public directory
  log INFO "Setting ownership and permissions for Hugo public directory"
  chmod -R 755 "$HUGO_PUBLIC_DIR"

  # 4. Set ownership and permissions for Hugo directory and related paths
  log INFO "Setting ownership and permissions for Hugo directory"
  chown -R caddy:caddy "$HUGO_DIR"
  chmod o+rx "$SAWYER_HOME"
  chmod o+rx "$GITHUB_DIR"
  chmod o+rx "$HUGO_DIR"
  chmod o+rx "/home/sawyer/github/hugo/dunamismax.com"
  chown -R www-data:www-data "$HUGO_PUBLIC_DIR"

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
# Function: dotfiles_load
# ------------------------------------------------------------------------------
# Copies specified dotfiles into /home/sawyer and ~/.config
# Adjust permissions, ownership, or backup logic as desired.
# ------------------------------------------------------------------------------
dotfiles_load() {
  log INFO "Creating necessary directories..."
  mkdir -p /home/sawyer/.config

  log INFO "Copying dotfiles to /home/sawyer..."
  cp /home/sawyer/github/bash/dotfiles/.bash_profile /home/sawyer/
  cp /home/sawyer/github/bash/dotfiles/.bashrc       /home/sawyer/
  cp /home/sawyer/github/bash/dotfiles/.fehbg        /home/sawyer/
  cp /home/sawyer/github/bash/dotfiles/.profile      /home/sawyer/
  cp /home/sawyer/github/bash/dotfiles/.Xresources   /home/sawyer/
  cp /home/sawyer/github/bash/dotfiles/.xprofile     /home/sawyer/
  cp /home/sawyer/github/bash/dotfiles/chrony.conf   /etc/chrony/
  cp /home/sawyer/github/bash/dotfiles/Caddyfile     /etc/caddy/

  log INFO "Copying config directories to /home/sawyer/.config..."
  cp -r /home/sawyer/github/bash/dotfiles/bin        /home/sawyer/.local/
  cp -r /home/sawyer/github/bash/dotfiles/i3         /home/sawyer/.config/
  cp -r /home/sawyer/github/bash/dotfiles/polybar    /home/sawyer/.config/
  cp -r /home/sawyer/github/bash/dotfiles/rofi       /home/sawyer/.config/
  cp -r /home/sawyer/github/bash/dotfiles/alacritty  /home/sawyer/.config/

  # Ensure correct ownership if running as root
  chown -R sawyer:sawyer /home/sawyer/
  chown caddy:caddy /etc/caddy/Caddyfile

  log INFO "Dotfiles copied successfully."
}

################################################################################
# Function: finalize_configuration
################################################################################
finalize_configuration() {
  log INFO "Finalizing system configuration..."

  cd /home/sawyer

  # Add Flatpak remote flathub repository if not already added
  log INFO "Adding Flatpak flathub repository..."
  if flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo; then
    log INFO "Flathub repository added or already exists."
  else
    log ERROR "Failed to add Flathub repository."
  fi

  # Upgrade installed packages
  log INFO "Upgrading installed packages..."
  if apt upgrade -y; then
    log INFO "Packages upgraded."
  else
    log ERROR "Package upgrade failed."
  fi

  # Configure Flatpak
  flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo

  # Update Flatpak applications
  log INFO "Updating Flatpak applications..."
  if flatpak update -y; then
    log INFO "Flatpak applications updated."
  else
    log ERROR "Failed to update Flatpak applications."
  fi

  # Refresh Snap packages (if Snap is installed)
  log INFO "Refreshing Snap packages..."
  if command -v snap &>/dev/null; then
    if snap refresh; then
      log INFO "Snap packages refreshed."
    else
      log ERROR "Failed to refresh Snap packages."
    fi
  else
    log INFO "Snap is not installed; skipping Snap refresh."
  fi

  # Clean up local package cache
  if apt clean; then
    log INFO "Package cache cleaned."
  else
    log ERROR "Failed to clean package cache."
  fi

  ##############################################################################
  # Additional System Logging Information
  ##############################################################################
  log INFO "Collecting system information..."

  # Uptime
  log INFO "System Uptime: $(uptime -p)"

  # Disk usage for root
  log INFO "Disk Usage (root): $(df -h / | tail -1)"

  # Memory usage
  log INFO "Memory Usage: $(free -h | grep Mem)"

  # CPU information
  CPU_MODEL=$(grep 'model name' /proc/cpuinfo | uniq | awk -F': ' '{print $2}')
  log INFO "CPU Model: ${CPU_MODEL:-Unknown}"

  # Kernel version
  log INFO "Kernel Version: $(uname -r)"

  # Network configuration
  log INFO "Network Configuration: $(ip addr show)"

  # End of system information collection
  log INFO "System information logged."

  log INFO "System configuration finalized."
}

################################################################################
# MAIN
################################################################################
main() {
  log INFO "--------------------------------------"
  log INFO "Starting Ubuntu Automated System Configuration Script"

# Bash script execution order:
  backup_system
  configure_ssh_settings
  force_release_ports
  bootstrap_and_install_pkgs
  configure_timezone "America/New_York"
  configure_ufw
  configure_ntp
  fail2ban
  install_all_build_dependencies
  install_and_enable_plex
  install_zig
  install_caddy
  download_repositories
  set_directory_permissions
  install_vscode_cli
  install_jetbrainsmono
  switch_to_pipewire
  install_gui
  dotfiles_load
  finalize_configuration

  log INFO "Configuration script finished successfully."
  log INFO "Enjoy Ubuntu!!!"
  log INFO "--------------------------------------"
}

# Entrypoint
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
