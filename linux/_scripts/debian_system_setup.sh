#!/usr/bin/env bash
################################################################################
# Debian Automated Setup & Hardening Script
#
# Description:
#   This script fully automates the configuration of a fresh Debian server,
#   creating a secure, optimized, and personalized environment suitable for
#   development and production deployments. Its comprehensive functions include:
#
#     • System Preparation:
#         - Verifies network connectivity
#         - Performs centralized package repository updates and upgrades.
#
#     • Package Installation:
#         - Installs essential system utilities, shells, editors, and CLI tools.
#         - Deploys development and build dependencies (compilers, libraries,
#           build systems, etc.) along with additional productivity utilities.
#
#     • Security Enhancements:
#         - Configures and hardens the OpenSSH server (custom ports, disable root
#           login, disable password authentication).
#         - Sets up and enables UFW firewall rules for critical services.
#         - Installs and configures fail2ban to protect against brute-force attacks.
#         - Applies kernel parameter tuning (sysctl) for system hardening.
#         - Enables persistent systemd journaling for improved log management.
#         - Configures unattended-upgrades for automatic security updates.
#
#     • Containerization & Third-Party Services:
#         - Installs and configures Docker and Docker Compose, including daemon
#           settings and user group modifications.
#         - Installs third-party applications such as Plex Media Server, Caddy
#           web server, and the Visual Studio Code CLI.
#
#     • Repository and Dotfiles Setup:
#         - Clones designated GitHub repositories and applies custom dotfiles.
#         - Sets correct permissions and secures configuration directories.
#
#     • Custom Service Deployment:
#         - Creates and enables custom systemd services for managing various
#           DunamisMax web applications (e.g., AI Agents, File Converter,
#           Messenger, Notes, and the Main Website).
#
#     • Finalization & Cleanup:
#         - Performs system cleanup, removes unnecessary packages, and logs
#           critical system information.
#         - Prompts for a system reboot to ensure all changes take effect.
#
# Usage:
#   Run this script as root (or via sudo). Adjust configuration variables
#   at the top of the script as needed to match your environment.
#
# Author : sawyer
# License: MIT
################################################################################


# ==============================================================================
# 1. CONFIGURATION & GLOBAL VARIABLES
# ==============================================================================
set -Eeuo pipefail
trap 'handle_error "Script failed at line $LINENO with exit code $?"' ERR

# Environment
export DEBIAN_FRONTEND=noninteractive

# Log file path (ensure the directory is writable)
LOG_FILE="/var/log/debian_setup.log"

# Default username to configure; if not present, it will be created.
USERNAME="sawyer"

# List of essential packages to install for a CLI-only environment
PACKAGES=(
  ###############################################
  # Shells, Terminal Multiplexers & Editors
  ###############################################
  bash                   # Bourne Again Shell
  zsh                    # Alternative shell with rich features
  fish                   # Friendly, feature-rich shell
  vim                    # Vi IMproved editor
  nano                   # Simple, user-friendly text editor
  emacs                  # Powerful text editor and IDE
  mc                     # Midnight Commander (text-based file manager)
  neovim                 # Modern Vim-based editor
  micro                  # Intuitive terminal text editor
  screen                 # Terminal multiplexer
  tmux                   # Terminal multiplexer
  zoxide                 # Smart directory jumper for faster “cd” navigation

  ###############################################
  # Development & Build Tools
  ###############################################
  nodejs                 # JavaScript runtime environment
  npm                    # Node package manager
  ninja-build            # High-speed build system
  meson                  # Modern build system for fast, user-friendly builds
  build-essential        # Essential compilation tools (gcc, make, etc.)
  cmake                  # Cross-platform build system
  intltool               # Internationalization tools
  gettext                # Localization and message extraction
  pigz                   # Parallel gzip implementation for faster compression
  libtool                # Generic library support script
  pkg-config             # Helper tool used when compiling applications
  libssl-dev             # SSL development libraries
  linux-headers-amd64    # Linux kernel headers
  bzip2                  # Compression utility
  libbz2-dev             # Development files for bzip2
  libffi-dev             # Foreign Function Interface library
  zlib1g-dev             # Compression library development files
  libreadline-dev        # GNU readline libraries for interactive input
  libsqlite3-dev         # SQLite3 development files
  xz-utils               # XZ compression utilities
  libncurses5-dev        # Development libraries for terminal handling
  python3                # Python programming language interpreter
  python3-dev            # Header files and static library for Python3
  python3-pip            # Python package installer
  python3-venv           # Lightweight virtual environment module for Python3
  libfreetype6-dev       # FreeType 2 font engine development files
  libglib2.0-dev         # GLib library for C programming
  debootstrap            # Tool to install a Debian base system
  git                    # Distributed version control system
  hugo                   # Static site generator

  ###############################################
  # System & Network Services
  ###############################################
  exim4                 # Mail transfer agent
  openssh-server        # Secure shell (SSH) server
  ufw                   # Uncomplicated Firewall
  acpid                 # Advanced Configuration and Power Interface daemon
  chrony                # Network time synchronization
  fail2ban              # Intrusion prevention software
  sudo                  # Execute commands as another user (usually root)
  passwd                # User password management
  bash-completion       # Command line completion for Bash
  logrotate              # Log file rotation utility
  net-tools              # Classic networking utilities (ifconfig, netstat, etc.)

  ###############################################
  # Virtualization & Storage
  ###############################################
  qemu-kvm              # Kernel-based Virtual Machine
  libvirt-daemon-system # Libvirt daemon for managing virtualization (system-wide)
  libvirt-clients       # Client utilities for libvirt
  virtinst              # Tools for virtual machine installation
  bridge-utils          # Utilities for configuring Ethernet bridges
  zfsutils-linux        # ZFS filesystem administration utilities
  docker.io             # Containerization platform

  ###############################################
  # Networking & Hardware Tools
  ###############################################
  curl                  # Command-line tool for transferring data with URLs
  wget                  # Non-interactive network downloader
  tcpdump               # Command-line packet analyzer
  rsync                 # Fast, versatile file copying tool
  nmap                  # Network exploration and security auditing tool
  lynx                  # Text-based web browser
  dnsutils              # DNS lookup utilities (dig, host, nslookup)
  iperf3                # Network performance measurement tool
  iftop                 # Real-time network bandwidth monitor
  mtr                   # Combined traceroute and ping tool for diagnostics
  iw                    # Wireless device configuration tool
  rfkill                # Query/modify wireless device status
  netcat-openbsd        # Modern netcat variant
  socat                 # Bidirectional data relay tool
  speedtest-cli         # CLI tool for internet speed tests

  ###############################################
  # Monitoring & Diagnostics
  ###############################################
  htop                  # Interactive process viewer
  neofetch              # System info tool for the terminal
  tig                   # Text-mode interface for Git
  jq                    # Command-line JSON processor
  vnstat                # Network traffic monitor
  tree                  # Tree-format directory listing
  fzf                   # Command-line fuzzy finder
  which                 # Locate a command’s executable path
  smartmontools         # Tools for monitoring storage device health
  lsof                  # List open files for diagnostics
  dstat                 # Versatile resource statistics tool
  sysstat               # Performance monitoring (iostat, mpstat, etc.)
  iotop                 # Monitor per-process disk I/O usage
  inotify-tools         # Monitor filesystem events via inotify
  pv                    # Monitor progress of data through pipelines
  nethogs               # Grouped process-based network monitor
  strace                # Trace system calls and signals
  ltrace                # Trace library calls
  atop                  # Advanced system and process monitor

  ###############################################
  # Filesystem & Disk Utilities
  ###############################################
  gdisk                 # GPT partition table manipulator
  ntfs-3g               # NTFS read/write driver for Linux
  ncdu                  # Ncurses-based disk usage analyzer
  unzip                 # Unzip utility for ZIP archives
  p7zip-full            # 7-Zip file archiver with high compression ratio
  parted                # Partitioning tool
  lvm2                  # Logical Volume Manager

  ###############################################
  # Scripting & Productivity Tools
  ###############################################
  perl                  # Practical Extraction and Report Language
  patch                 # Apply patch files to source code
  bc                    # Arbitrary precision calculator language
  parallel              # Execute jobs in parallel
  gawk                  # GNU version of awk for text processing
  expect                # Automates interactive applications

  ###############################################
  # Code Navigation & Developer Productivity
  ###############################################
  exuberant-ctags       # Generate tag files for source code navigation
  fd-find               # Modern alternative to the find command
  bat                   # cat clone with syntax highlighting (installed as 'batcat' on Debian)
  exa                   # Modern replacement for ls with extra features
  ripgrep               # Fast recursive search tool (improved grep)
  delta                 # Enhanced git diff viewer with syntax highlighting
  hyperfine             # Benchmarking tool for command-line programs
  cheat                 # Command-line cheat sheet tool

  ###############################################
  # Multimedia & Other Applications
  ###############################################
  ffmpeg                # Multimedia framework for audio/video processing
  restic                # Fast, efficient backup program
  imagemagick           # Image manipulation and conversion suite
  mpv                   # Lightweight media player
)

# Additional widely-used CLI utilities and best-practice tools
EXTRA_PACKAGES=(
  ###############################################
  # Terminal Enhancements & File Management
  ###############################################
  byobu              # Enhanced terminal multiplexer (wrapper for tmux/screen)
  ranger             # Terminal file manager with vi-style key bindings
  nnn                # Minimal, fast file manager alternative

  ###############################################
  # Communication & Productivity
  ###############################################
  mutt               # Text-based email client
  newsboat           # Terminal RSS feed reader
  irssi              # Terminal-based IRC client
  weechat            # Extensible IRC client with scripting support
  httpie             # User-friendly HTTP client
  youtube-dl         # Command-line video downloader
  thefuck            # Auto-corrects mistyped commands

  ###############################################
  # Task & Calendar Management
  ###############################################
  taskwarrior        # Powerful CLI task management tool
  calcurse           # Text-based calendar and scheduling application

  ###############################################
  # System Monitoring & Performance
  ###############################################
  glances            # Cross-platform system monitoring tool with web/UI options
  bpytop             # Modern resource monitor (CPU, memory, network)

  ###############################################
  # Code & Text Processing Enhancements
  ###############################################
  silversearcher-ag  # Fast code searching tool (The Silver Searcher)
  asciinema          # Terminal session recorder for sharing demos
  tldr               # Simplified, community-maintained command summaries

  ###############################################
  # Fun & Miscellaneous
  ###############################################
  cowsay             # Fun tool that displays messages as a talking cow
  fortune-mod        # Displays random fortunes or quotes
  lolcat             # Rainbow-colorizes terminal output
  figlet             # Creates large ASCII art text banners
  cmatrix            # “The Matrix” digital rain screensaver
)


# ------------------------------------------------------------------------------
# Nord Color Theme (Enhanced)
# ------------------------------------------------------------------------------
# 24-bit ANSI escape sequences for an attractive Nord-inspired color palette.
RED='\033[38;2;191;97;106m'      # Error messages
YELLOW='\033[38;2;235;203;139m'   # Warnings and labels
GREEN='\033[38;2;163;190;140m'    # Success and info
BLUE='\033[38;2;94;129;172m'      # Debug and highlights
CYAN='\033[38;2;136;192;208m'     # Headings and accents
MAGENTA='\033[38;2;180;142;173m'  # Additional accents
GRAY='\033[38;2;216;222;233m'     # Light gray text
NC='\033[0m'                     # Reset color

# ==============================================================================
# 2. UTILITY & LOGGING FUNCTIONS
# ==============================================================================

# Log messages with timestamp, level, and color-coded output.
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

# Log a warning message (non-fatal)
warn() {
    log WARN "$@"
}

# Handle fatal errors and exit the script.
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

# Ensure the specified user exists; if not, create it.
ensure_user() {
    if id "$USERNAME" &>/dev/null; then
        log INFO "User '$USERNAME' already exists."
    else
        log INFO "User '$USERNAME' does not exist. Creating user..."
        useradd -m -s /bin/bash "$USERNAME" || handle_error "Failed to create user $USERNAME."
        log INFO "User '$USERNAME' created successfully."
    fi
}

# Check network connectivity
check_network() {
    if ! ping -c 1 google.com &>/dev/null; then
        handle_error "No network connectivity. Please check your network settings."
    else
        log INFO "Network connectivity verified."
    fi
}

# Centralized system update and upgrade.
update_system() {
    log INFO "Updating package repositories..."
    apt update || handle_error "Failed to update package repositories."
    log INFO "Upgrading installed packages..."
    apt upgrade -y || handle_error "Failed to upgrade packages."
    log INFO "System update and upgrade completed successfully."
}

# ==============================================================================
# 4. CORE CONFIGURATION FUNCTIONS
# ==============================================================================

configure_ssh() {
    log INFO "Configuring OpenSSH Server..."
    if ! dpkg -l | grep -qw openssh-server; then
        apt install -y openssh-server || handle_error "Failed to install OpenSSH Server."
        log INFO "OpenSSH Server installed."
    else
        log INFO "OpenSSH Server is already installed."
    fi

    systemctl enable --now ssh || handle_error "Failed to enable/start SSH service."

    local sshd_config="/etc/ssh/sshd_config"
    local backup="${sshd_config}.bak.$(date +%Y%m%d%H%M%S)"
    cp "$sshd_config" "$backup" || handle_error "Failed to backup sshd_config."
    log INFO "Backed up sshd_config to $backup."

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

    systemctl restart ssh || handle_error "Failed to restart SSH service."
    log INFO "SSH configuration updated successfully."
}

install_packages() {
    log INFO "Installing essential packages..."
    local to_install=()
    for pkg in "${PACKAGES[@]}"; do
        if ! dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "install ok installed"; then
            to_install+=("$pkg")
        else
            log INFO "Package $pkg is already installed."
        fi
    done

    if [ "${#to_install[@]}" -gt 0 ]; then
        log INFO "Installing packages: ${to_install[*]}"
        apt install -y "${to_install[@]}" || handle_error "Failed to install essential packages."
    else
        log INFO "All essential packages are already installed."
    fi
}

install_extra_packages() {
    log INFO "Installing essential packages..."
    local to_install=()
    for pkg in "${EXTRA_PACKAGES[@]}"; do
        if ! dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "install ok installed"; then
            to_install+=("$pkg")
        else
            log INFO "Package $pkg is already installed."
        fi
    done

    if [ "${#to_install[@]}" -gt 0 ]; then
        log INFO "Installing packages: ${to_install[*]}"
        apt install -y "${to_install[@]}" || handle_error "Failed to install extra packages."
    else
        log INFO "All extra packages are already installed."
    fi
}

configure_ufw() {
    log INFO "Configuring UFW firewall..."
    systemctl enable ufw || handle_error "Failed to enable UFW."
    systemctl start ufw || handle_error "Failed to start UFW."
    ufw --force enable || handle_error "Failed to activate UFW."

    local rules=(
        "allow ssh"
        "allow http"
        "allow https"
        "allow 32400/tcp"  # Plex Media Server
    )
    for rule in "${rules[@]}"; do
        ufw $rule || warn "Could not apply UFW rule: $rule"
        log INFO "Applied UFW rule: $rule"
    done

    log INFO "UFW firewall configuration completed."
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
    if ! dpkg-query -W -f='${Status}' fail2ban 2>/dev/null | grep -q "install ok installed"; then
        apt install -y fail2ban || handle_error "Failed to install fail2ban."
        log INFO "fail2ban installed successfully."
    else
        log INFO "fail2ban is already installed."
    fi

    systemctl enable fail2ban || handle_error "Failed to enable fail2ban."
    systemctl start fail2ban || handle_error "Failed to start fail2ban."
    log INFO "fail2ban configured successfully."
}

configure_journald() {
    log INFO "Configuring systemd journal for persistent logging..."
    mkdir -p /var/log/journal || handle_error "Failed to create /var/log/journal directory."
    systemctl restart systemd-journald || warn "Failed to restart systemd-journald."
    log INFO "Systemd journal is now configured for persistent logging."
}

install_build_dependencies() {
    log INFO "Installing build dependencies..."
    local deps=(
        build-essential make gcc g++ clang cmake git curl wget vim tmux unzip zip
        ca-certificates software-properties-common apt-transport-https gnupg lsb-release
        jq pkg-config libssl-dev libbz2-dev libffi-dev zlib1g-dev libreadline-dev
        libsqlite3-dev tk-dev libncurses5-dev libncursesw5-dev libgdbm-dev libnss3-dev
        liblzma-dev xz-utils libxml2-dev libxmlsec1-dev gdb llvm
    )
    apt install -y --no-install-recommends "${deps[@]}" || handle_error "Failed to install build dependencies."

    log INFO "Installing Rust toolchain..."
    if ! command -v rustc &>/dev/null; then
        curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y || handle_error "Rust toolchain installation failed."
        export PATH="$HOME/.cargo/bin:$PATH"
        log INFO "Rust toolchain installed successfully."
    else
        log INFO "Rust toolchain is already installed."
    fi

    log INFO "Installing Go..."
    apt install -y golang-go || handle_error "Failed to install Go."
    log INFO "Build dependencies installed successfully."
}

install_caddy() {
    log INFO "Installing Caddy web server..."
    apt install -y debian-archive-keyring apt-transport-https curl || handle_error "Failed to install prerequisites for Caddy."
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --batch --yes --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg \
        || handle_error "Failed to add Caddy GPG key."
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        | tee /etc/apt/sources.list.d/caddy-stable.list || handle_error "Failed to add Caddy repository."
    apt update || handle_error "Failed to update repositories after adding Caddy repository."
    apt install -y caddy || handle_error "Failed to install Caddy."
    log INFO "Caddy web server installed successfully."
}

install_plex() {
    log INFO "Installing Plex Media Server..."
    if dpkg -s plexmediaserver >/dev/null 2>&1; then
        log INFO "Plex Media Server is already installed."
        return
    fi

    apt install -y curl || handle_error "Failed to install curl for Plex."
    local DEB_URL="https://downloads.plex.tv/plex-media-server-new/1.41.3.9314-a0bfb8370/debian/plexmediaserver_1.41.3.9314-a0bfb8370_amd64.deb"
    log INFO "Downloading Plex package..."
    curl -LO "${DEB_URL}" || handle_error "Failed to download Plex package."
    log INFO "Installing Plex Media Server..."
    dpkg -i "${DEB_PACKAGE}" || { apt install -f -y && dpkg -i "${DEB_PACKAGE}" || handle_error "Failed to install Plex Media Server."; }
    dpkg --configure -a || warn "Some packages failed to configure; continuing..."
    systemctl enable plexmediaserver || handle_error "Failed to enable Plex service."
    systemctl start plexmediaserver || handle_error "Failed to start Plex service."
    log INFO "Plex Media Server installed and running successfully."
}

install_vscode_cli() {
    log INFO "Installing Visual Studio Code CLI..."
    if [ -e "/usr/local/node" ]; then
        rm -f "/usr/local/node" || handle_error "Failed to remove existing /usr/local/node."
    fi
    ln -s "$(which node)" /usr/local/node || handle_error "Failed to create symbolic link for Node.js."
    log INFO "Downloading VSCode CLI..."
    curl -Lk 'https://code.visualstudio.com/sha/download?build=stable&os=cli-alpine-x64' --output vscode_cli.tar.gz \
        || handle_error "Failed to download VSCode CLI."
    tar -xf vscode_cli.tar.gz || handle_error "Failed to extract VSCode CLI."
    rm -f vscode_cli.tar.gz || warn "Failed to remove VSCode CLI tarball."
    log INFO "Visual Studio Code CLI installed successfully. Run './code tunnel --name debian-server' to start the tunnel."
}

setup_repos_and_dotfiles() {
    log INFO "Setting up GitHub repositories and dotfiles..."
    local GITHUB_DIR="/home/${USERNAME}/github"
    local USER_HOME="/home/${USERNAME}"
    mkdir -p "$GITHUB_DIR" || handle_error "Failed to create GitHub directory: $GITHUB_DIR"
    cd "$GITHUB_DIR" || handle_error "Failed to change directory to $GITHUB_DIR"

    local repos=("bash" "c" "religion" "windows" "hugo" "python")
    for repo in "${repos[@]}"; do
        local repo_dir="${GITHUB_DIR}/${repo}"
        local repo_url="https://github.com/dunamismax/${repo}.git"
        rm -rf "$repo_dir" 2>/dev/null
        git clone "$repo_url" "$repo_dir" || handle_error "Failed to clone repository: $repo"
        log INFO "Cloned repository: $repo"
    done

    # Configure permissions for Hugo directories
    local HUGO_PUBLIC_DIR="${GITHUB_DIR}/hugo/dunamismax.com/public"
    local HUGO_DIR="${GITHUB_DIR}/hugo"
    if [[ -d "$HUGO_PUBLIC_DIR" ]]; then
        chown -R www-data:www-data "$HUGO_PUBLIC_DIR" || handle_error "Failed to set ownership for Hugo public directory."
        chmod -R 755 "$HUGO_PUBLIC_DIR" || handle_error "Failed to set permissions for Hugo public directory."
    else
        warn "Hugo public directory not found: $HUGO_PUBLIC_DIR"
    fi

    if [[ -d "$HUGO_DIR" ]]; then
        chown -R caddy:caddy "$HUGO_DIR" || handle_error "Failed to set ownership for Hugo directory."
        chmod o+rx "$USER_HOME" "$GITHUB_DIR" "$HUGO_DIR" "${HUGO_DIR}/dunamismax.com" \
            || handle_error "Failed to set permissions for Hugo directory."
    else
        warn "Hugo directory not found: $HUGO_DIR"
    fi

    for repo in bash c python religion windows; do
        local repo_dir="${GITHUB_DIR}/${repo}"
        if [[ -d "$repo_dir" ]]; then
            chown -R "${USERNAME}:${USERNAME}" "$repo_dir" || handle_error "Failed to set ownership for repository: $repo"
        else
            warn "Repository directory not found: $repo_dir"
        fi
    done

    # Make all .sh files executable
    find "$GITHUB_DIR" -type f -name "*.sh" -exec chmod +x {} + || handle_error "Failed to set executable permissions for .sh files."

    # Secure .git directories
    local DIR_PERMISSIONS="700"
    local FILE_PERMISSIONS="600"
    while IFS= read -r -d '' git_dir; do
        chmod "$DIR_PERMISSIONS" "$git_dir" || handle_error "Failed to set permissions for $git_dir"
        find "$git_dir" -type d -exec chmod "$DIR_PERMISSIONS" {} + || handle_error "Failed to set directory permissions for $git_dir"
        find "$git_dir" -type f -exec chmod "$FILE_PERMISSIONS" {} + || handle_error "Failed to set file permissions for $git_dir"
    done < <(find "$GITHUB_DIR" -type d -name ".git" -print0)

    # Load dotfiles from repository
    local dotfiles_dir="${USER_HOME}/github/bash/linux/dotfiles"
    if [[ ! -d "$dotfiles_dir" ]]; then
        handle_error "Dotfiles directory not found: $dotfiles_dir"
    fi

    local config_dir="${USER_HOME}/.config"
    local local_bin_dir="${USER_HOME}/.local/bin"
    mkdir -p "$config_dir" "$local_bin_dir" || handle_error "Failed to create config directories."

    for file in .bashrc .profile .fehbg; do
        cp "${dotfiles_dir}/${file}" "${USER_HOME}/${file}" || warn "Failed to copy ${file}."
    done

    cp "${dotfiles_dir}/Caddyfile" /etc/caddy/Caddyfile || handle_error "Failed to copy Caddyfile."
    for dir in i3 i3status alacritty picom; do
        cp -r "${dotfiles_dir}/${dir}" "$config_dir/" || warn "Failed to copy configuration directory: $dir"
    done

    cp -r "${dotfiles_dir}/bin" "$local_bin_dir" || warn "Failed to copy bin directory."

    chown -R "${USERNAME}:${USERNAME}" "$USER_HOME" || handle_error "Failed to set ownership for $USER_HOME."
    chown caddy:caddy /etc/caddy/Caddyfile || handle_error "Failed to set ownership for Caddyfile."
    chmod -R u=rwX,g=rX,o=rX "$local_bin_dir" || handle_error "Failed to set permissions for $local_bin_dir."

    log INFO "Repositories and dotfiles setup completed successfully."
    cd ~ || handle_error "Failed to return to home directory."
}

enable_dunamismax_services() {
  log INFO "Enabling DunamisMax website services..."

  cat << 'EOF' > /etc/systemd/system/dunamismax-ai-agents.service
[Unit]
Description=DunamisMax AI Agents Service
After=network.target

[Service]
User=sawyer
Group=sawyer
WorkingDirectory=/home/sawyer/github/web/ai_agents
Environment="PATH=/home/sawyer/github/web/ai_agents/.venv/bin"
EnvironmentFile=/home/sawyer/github/web/ai_agents/.env
ExecStart=/home/sawyer/github/web/ai_agents/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8200
Restart=always

[Install]
WantedBy=multi-user.target
EOF

  cat << 'EOF' > /etc/systemd/system/dunamismax-files.service
[Unit]
Description=DunamisMax File Converter Service
After=network.target

[Service]
User=sawyer
Group=sawyer
WorkingDirectory=/home/sawyer/github/web/converter_service
Environment="PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/home/sawyer/github/web/converter_service/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8300
Restart=always

[Install]
WantedBy=multi-user.target
EOF

  cat << 'EOF' > /etc/systemd/system/dunamismax-messenger.service
[Unit]
Description=DunamisMax Messenger
After=network.target

[Service]
User=sawyer
Group=sawyer
WorkingDirectory=/home/sawyer/github/web/messenger
Environment="PATH=/home/sawyer/github/web/messenger/.venv/bin"
ExecStart=/home/sawyer/github/web/messenger/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8100
Restart=always

[Install]
WantedBy=multi-user.target
EOF

  cat << 'EOF' > /etc/systemd/system/dunamismax-notes.service
[Unit]
Description=DunamisMax Notes Page
After=network.target

[Service]
User=sawyer
Group=sawyer
WorkingDirectory=/home/sawyer/github/web/notes
Environment="PATH=/home/sawyer/github/web/notes/.venv/bin"
ExecStart=/home/sawyer/github/web/notes/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8500
Restart=always

[Install]
WantedBy=multi-user.target
EOF

  cat << 'EOF' > /etc/systemd/system/dunamismax.service
[Unit]
Description=DunamisMax Main Website
After=network.target

[Service]
User=sawyer
Group=sawyer
WorkingDirectory=/home/sawyer/github/web/dunamismax
Environment="PATH=/home/sawyer/github/web/dunamismax/.venv/bin"
ExecStart=/home/sawyer/github/web/dunamismax/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable dunamismax-ai-agents.service
  systemctl enable dunamismax-files.service
  systemctl enable dunamismax-messenger.service
  systemctl enable dunamismax-notes.service
  systemctl enable dunamismax.service

  systemctl start dunamismax-ai-agents.service
  systemctl start dunamismax-files.service
  systemctl start dunamismax-messenger.service
  systemctl start dunamismax-notes.service
  systemctl start dunamismax.service

  log INFO "DunamisMax services enabled and started."
}

# ==============================================================================
# 5. ADDITIONAL SECURITY & AUTOMATION FUNCTIONS
# ==============================================================================

# Enable unattended-upgrades for automatic security updates.
configure_unattended_upgrades() {
    log INFO "Configuring unattended-upgrades for automatic security updates..."
    apt install -y unattended-upgrades || handle_error "Failed to install unattended-upgrades."
    # Configure auto-updates (adjust values as desired)
    cat <<EOF >/etc/apt/apt.conf.d/20auto-upgrades
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
    systemctl enable unattended-upgrades || warn "Could not enable unattended-upgrades service."
    log INFO "Unattended-upgrades configured successfully."
}

# Apply additional system hardening via sysctl.
system_hardening() {
    log INFO "Applying additional system hardening..."
    cat <<EOF >/etc/sysctl.d/99-harden.conf
# Disable packet forwarding by default
net.ipv4.ip_forward = 0
net.ipv6.conf.all.forwarding = 0

# Disable ICMP redirects and source routing
net.ipv4.conf.all.accept_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0

# Enable TCP SYN cookies to protect against SYN flood attacks
net.ipv4.tcp_syncookies = 1

# Enable reverse path filtering
net.ipv4.conf.all.rp_filter = 1

# Ignore ICMP broadcast requests
net.ipv4.icmp_echo_ignore_broadcasts = 1
EOF
    sysctl --system || warn "Failed to reload sysctl settings."
    log INFO "System hardening applied."
}

# ==============================================================================
# 6. DOCKER INSTALLATION & CONFIGURATION
# ==============================================================================

install_docker() {
    log INFO "Installing Docker..."
    if command -v docker &>/dev/null; then
        log INFO "Docker is already installed."
    else
        apt install -y apt-transport-https ca-certificates curl gnupg lsb-release || handle_error "Failed to install Docker prerequisites."
        curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --batch --yes --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
            || handle_error "Failed to add Docker GPG key."
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] \
https://download.docker.com/linux/debian $(lsb_release -cs) stable" \
            | tee /etc/apt/sources.list.d/docker.list > /dev/null || handle_error "Failed to set up Docker repository."
        apt update || handle_error "Failed to update package repositories for Docker."
        apt install -y docker-ce docker-ce-cli containerd.io || handle_error "Failed to install Docker."
        log INFO "Docker installed successfully."
    fi

    # Add the specified user to the docker group.
    usermod -aG docker "$USERNAME" || warn "Failed to add $USERNAME to the docker group."

    # Configure Docker daemon settings.
    mkdir -p /etc/docker
    cat <<EOF >/etc/docker/daemon.json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "exec-opts": ["native.cgroupdriver=systemd"]
}
EOF
    systemctl enable docker || warn "Could not enable Docker service."
    systemctl restart docker || handle_error "Failed to restart Docker."
    log INFO "Docker configuration completed."
}

# Docker Compose
install_docker_compose() {
    log INFO "Installing Docker Compose..."
    if ! command -v docker-compose &>/dev/null; then
        # Specify the desired Docker Compose version.
        local version="2.20.2"
        curl -L "https://github.com/docker/compose/releases/download/v${version}/docker-compose-$(uname -s)-$(uname -m)" \
            -o /usr/local/bin/docker-compose || handle_error "Failed to download Docker Compose."
        chmod +x /usr/local/bin/docker-compose || handle_error "Failed to set executable permission on Docker Compose."
        log INFO "Docker Compose installed successfully."
    else
        log INFO "Docker Compose is already installed."
    fi
}


# ==============================================================================
# 7. FINALIZATION & CLEANUP
# ==============================================================================

cleanup_system() {
    log INFO "Cleaning up unnecessary packages..."
    apt autoremove -y || warn "Failed to remove orphaned packages."
    apt autoclean -y || warn "Failed to autoclean package cache."
    log INFO "System cleanup completed."
}

finalize_configuration() {
    log INFO "Finalizing system configuration and cleanup..."
    cleanup_system
    cd "/home/${USERNAME}" || handle_error "Failed to change to user home directory."

    apt clean || warn "Failed to clean package cache."

    log INFO "Collecting system information..."
    log INFO "Uptime: $(uptime -p)"
    log INFO "Disk Usage (root): $(df -h / | tail -1)"
    log INFO "Memory Usage: $(free -h | grep Mem)"
    local cpu_model
    cpu_model=$(grep 'model name' /proc/cpuinfo | head -1 | awk -F': ' '{print $2}')
    log INFO "CPU Model: ${cpu_model:-Unknown}"
    log INFO "Kernel Version: $(uname -r)"
    log INFO "Network Configuration:"
    ip addr show | sed "s/^/    /"
    log INFO "Final system configuration completed."
}

prompt_reboot() {
    log INFO "Setup complete. A system reboot is recommended to apply all changes."
    read -rp "Reboot now? (y/n): " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        log INFO "Rebooting system..."
        reboot
    else
        log INFO "Reboot skipped. Please reboot manually when convenient."
    fi
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
    log INFO "Starting Debian Automated Setup Script"
    log INFO "======================================"

    # Pre-checks
    if [[ $(id -u) -ne 0 ]]; then
        handle_error "This script must be run as root. Please use sudo."
    fi

    check_network
    update_system
    ensure_user
    configure_ssh
    install_packages
    install_extra_packages
    configure_ufw
    configure_journald
    release_ports
    configure_fail2ban
    install_build_dependencies
    install_plex
    install_vscode_cli
    install_caddy
    setup_repos_and_dotfiles
    enable_dunamismax_services
    configure_unattended_upgrades
    system_hardening
    install_docker
    install_docker_compose

    finalize_configuration

    log INFO "Debian system setup completed successfully."
    prompt_reboot
}

# Execute main if script is run directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
