#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Arch Linux Automated Setup Script (Non-Interactive, with yay)
# ------------------------------------------------------------------------------
#  • Installs yay at the start.
#  • Uses yay for AUR packages (e.g., Plex, PowerShell, xfce-polkit).
#  • Uses pacman for official packages (base-devel, caddy, etc.).
#  • Automates fresh system configuration with minimal to no user interaction.
#
#  • Logs actions/errors to /var/log/arch_setup.log with timestamps.
#
# Author: dunamismax | License: MIT
# ------------------------------------------------------------------------------

set -Eeuo pipefail

# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/arch_setup.log"
VERBOSE=2
USERNAME="sawyer"

# -- Official packages (installed via pacman) ----------------------------------
OFFICIAL_PACKAGES=(
  # Core & dev
  base-devel
  cmake
  ninja
  meson
  git
  curl
  wget
  rsync
  jq
  neofetch
  htop
  tmux
  screen
  tree
  fzf
  nano
  vim
  neovim
  mc
  python
  python-pip
  go
  # Networking & system
  openssh
  ufw
  fail2ban
  chrony
  lsof
  net-tools
  nmap
  tcpdump
  acpid
  # Fonts & theming
  ttf-dejavu
  ttf-liberation
  ttf-hack
  ttf-font-awesome
  papirus-icon-theme
  # Multimedia & extras
  ffmpeg
  restic
  ntfs-3g
  smartmontools
  cups
  # Virtualization
  qemu
  libvirt
  virt-manager
  bridge-utils
  # GUI environment
  xorg
  lightdm
  xfce4
  xfce4-goodies
  i3
  i3blocks
  rofi
  feh
  polybar
  picom
  alacritty
  ranger
  pavucontrol
  alsa-utils
  # Misc
  bash-completion
  lynx
  which
  patch
  flameshot
  hugo
  # Caddy from official repos
  caddy
)

# -- AUR packages (installed via yay) ------------------------------------------
AUR_PACKAGES=(
  # Powershell (bin version)
  powershell-bin
  # Plex Media Server
  plex-media-server
  # xfce-polkit (polkit agent for Xfce)
  xfce-polkit
  # JetBrains Mono font (can also be in [community], but included here for demonstration)
  ttf-jetbrains-mono
)

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
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

    # Ensure the log file exists
    if [[ -z "${LOG_FILE:-}" ]]; then
        LOG_FILE="/var/log/arch_setup.log"
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

# ------------------------------------------------------------------------------
# ERROR HANDLING
# ------------------------------------------------------------------------------
trap 'log ERROR "Script failed at line $LINENO. See above for details."' ERR

if [[ $(id -u) -ne 0 ]]; then
  echo "This script must be run as root (e.g., sudo $0). Exiting."
  exit 1
fi

# ------------------------------------------------------------------------------
# Install yay Non-Interactively
# ------------------------------------------------------------------------------
install_yay() {
  log INFO "Checking if 'yay' is installed..."
  if ! command -v yay &>/dev/null; then
    log INFO "Installing yay from AUR (non-interactive)..."
    pacman --noconfirm --needed -S git base-devel
    cd /tmp
    rm -rf yay
    git clone https://aur.archlinux.org/yay.git
    cd yay
    # Build & install with no user prompts
    sudo -u "$USERNAME" makepkg -si --noconfirm
    cd /
    rm -rf /tmp/yay
    log INFO "yay installed successfully."
  else
    log INFO "yay is already installed."
  fi
}

# ------------------------------------------------------------------------------
# BACKUP SYSTEM (using rsync)
# ------------------------------------------------------------------------------
backup_system() {
  pacman --noconfirm --needed -S rsync

  local SOURCE="/"
  local DESTINATION="/home/${USERNAME}/BACKUPS"
  local TIMESTAMP
  TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
  local BACKUP_FOLDER="$DESTINATION/backup-$TIMESTAMP"
  local RETENTION_DAYS=7

  mkdir -p "$BACKUP_FOLDER"

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
    "/root/.cache/*"
    "/home/*/.cache/*"
    "$DESTINATION"
  )
  local EXCLUDES_ARGS=()
  for EXCLUDE in "${EXCLUDES[@]}"; do
    EXCLUDES_ARGS+=(--exclude="$EXCLUDE")
  done

  log INFO "Starting system backup to $BACKUP_FOLDER"
  if rsync -aAXv "${EXCLUDES_ARGS[@]}" "$SOURCE" "$BACKUP_FOLDER"; then
    log INFO "Backup completed successfully: $BACKUP_FOLDER"
  else
    log ERROR "Error: Backup process failed."
    exit 1
  fi

  log INFO "Cleaning up old backups older than $RETENTION_DAYS days."
  find "$DESTINATION" -type d -name "backup-*" -mtime +"$RETENTION_DAYS" -exec rm -rf {} \; || \
    log WARN "Warning: Failed to remove some old backups."
}

# ------------------------------------------------------------------------------
# CONFIGURE SSH
# ------------------------------------------------------------------------------
configure_ssh_settings() {
  log INFO "Installing and enabling OpenSSH Server..."

  if ! pacman -Qi openssh &>/dev/null; then
    pacman --noconfirm -S openssh
    log INFO "OpenSSH installed."
  else
    log INFO "OpenSSH is already installed."
  fi

  systemctl enable --now sshd
  log INFO "sshd.service enabled and started."

  local sshd_config="/etc/ssh/sshd_config"
  local backup_file="${sshd_config}.bak.$(date +%Y%m%d%H%M%S)"
  cp "$sshd_config" "$backup_file"

  declare -A sshd_settings=(
    ["Port"]="22"
    ["MaxAuthTries"]="8"
    ["MaxSessions"]="6"
    ["PermitRootLogin"]="no"
    ["Protocol"]="2"
  )

  for setting in "${!sshd_settings[@]}"; do
    if grep -q "^${setting} " "$sshd_config"; then
      sed -i "s/^${setting} .*/${setting} ${sshd_settings[$setting]}/" "$sshd_config"
    else
      echo "${setting} ${sshd_settings[$setting]}" >> "$sshd_config"
    fi
  done

  if systemctl restart sshd; then
    log INFO "sshd restarted successfully."
  else
    log ERROR "Failed to restart sshd. Check configuration."
    return 1
  fi
}

# ------------------------------------------------------------------------------
# FORCE RELEASE PORTS
# ------------------------------------------------------------------------------
force_release_ports() {
  log INFO "Removing apache (httpd) if installed..."
  if pacman -Qi apache &>/dev/null; then
    pacman --noconfirm -Rns apache
  fi

  log INFO "Installing net-tools & lsof if needed..."
  pacman --noconfirm --needed -S net-tools lsof

  local tcp_ports=("8080" "80" "443" "32400" "8324" "32469")
  local udp_ports=("80" "443" "1900" "5353" "32410" "32411" "32412" "32413" "32414" "32415")

  log INFO "Killing any processes on the specified ports..."

  for p in "${tcp_ports[@]}"; do
    local pids
    pids="$(lsof -t -i TCP:"$p" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "$pids" ]]; then
      log INFO "Killing processes on TCP port $p: $pids"
      kill -9 $pids || true
    fi
  done

  for p in "${udp_ports[@]}"; do
    local pids
    pids="$(lsof -t -i UDP:"$p" 2>/dev/null || true)"
    if [[ -n "$pids" ]]; then
      log INFO "Killing processes on UDP port $p: $pids"
      kill -9 $pids || true
    fi
  done

  log INFO "Ports forcibly released."
}

# ------------------------------------------------------------------------------
# INSTALL OFFICIAL PACKAGES (PACMAN)
# ------------------------------------------------------------------------------
install_official_packages() {
  log INFO "Running pacman -Syu (non-interactive)..."
  pacman --noconfirm -Syu

  for pkg in "${OFFICIAL_PACKAGES[@]}"; do
    if ! pacman -Qi "$pkg" &>/dev/null; then
      log INFO "Installing official package: $pkg"
      pacman --noconfirm --needed -S "$pkg"
    else
      log INFO "Package '$pkg' is already installed."
    fi
  done
}

# ------------------------------------------------------------------------------
# INSTALL AUR PACKAGES (YAY)
# ------------------------------------------------------------------------------
install_aur_packages() {
  for pkg in "${AUR_PACKAGES[@]}"; do
    if ! pacman -Qs "$pkg" &>/dev/null; then
      log INFO "Installing AUR package: $pkg"
      sudo -u "$USERNAME" yay --noconfirm --needed -S "$pkg"
    else
      log INFO "AUR package '$pkg' is already installed."
    fi
  done
}

# ------------------------------------------------------------------------------
# CONFIGURE UFW
# ------------------------------------------------------------------------------
configure_ufw() {
  systemctl enable ufw.service
  systemctl start ufw.service

  ufw --force enable

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

# ------------------------------------------------------------------------------
# CONFIGURE TIMEZONE
# ------------------------------------------------------------------------------
configure_timezone() {
  local tz="${1:-UTC}"
  log INFO "Setting timezone to ${tz}..."
  ln -sf "/usr/share/zoneinfo/${tz}" /etc/localtime
  hwclock --systohc
  log INFO "Timezone set to $tz."
}

# ------------------------------------------------------------------------------
# CONFIGURE NTP (CHRONY)
# ------------------------------------------------------------------------------
configure_ntp() {
  if ! pacman -Qi chrony &>/dev/null; then
    pacman --noconfirm -S chrony
  fi

  systemctl enable chronyd
  systemctl restart chronyd
  log INFO "Chrony installed and enabled."
}

# ------------------------------------------------------------------------------
# CONFIGURE FAIL2BAN
# ------------------------------------------------------------------------------
configure_fail2ban() {
  if ! pacman -Qi fail2ban &>/dev/null; then
    pacman --noconfirm -S fail2ban
  fi

  systemctl enable fail2ban
  systemctl start fail2ban
  log INFO "Fail2Ban installed and enabled."
}

# ------------------------------------------------------------------------------
# INSTALL ALL BUILD DEPS (Rust, etc.) - Some done in OFFICIAL_PACKAGES
# ------------------------------------------------------------------------------
install_all_build_dependencies() {
  log INFO "Updating system..."
  pacman --noconfirm -Syu

  # Rustup for the stable toolchain if not installed
  if ! pacman -Qi rustup &>/dev/null; then
    pacman --noconfirm -S rustup
    rustup default stable
  fi

  log INFO "All dev dependencies installed (base-devel, python, go, rustup, etc.)."
}

# ------------------------------------------------------------------------------
# INSTALL & ENABLE PLEX (AUR)
# ------------------------------------------------------------------------------
install_and_enable_plex() {
  if pacman -Qs plex-media-server &>/dev/null; then
    log INFO "Plex Media Server already installed. Skipping."
    return
  fi

  log INFO "Installing Plex (AUR) via yay..."
  sudo -u "$USERNAME" yay --noconfirm --needed -S plex-media-server

  systemctl enable plexmediaserver
  systemctl start plexmediaserver

  log INFO "Plex Media Server installation complete."
}

# ------------------------------------------------------------------------------
# INSTALL POWERSHELL AND ZIG (Powershell from AUR, Zig from official or AUR)
# ------------------------------------------------------------------------------
install_powershell_and_zig() {
  if command -v pwsh &>/dev/null; then
    log INFO "PowerShell already installed."
  else
    # Already included powershell-bin in AUR_PACKAGES
    log INFO "PowerShell will be installed via AUR. Skipping direct step."
  fi

  if command -v zig &>/dev/null; then
    log INFO "Zig already installed."
  else
    # If you prefer AUR dev builds, place 'zig-dev' in AUR_PACKAGES
    # If official, "zig" is in community
    if ! pacman -Qi zig &>/dev/null; then
      pacman --noconfirm --needed -S zig
    fi
    log INFO "Zig installed."
  fi
}

# ------------------------------------------------------------------------------
# INSTALL VSCode CLI (manually downloaded, as in original script)
# ------------------------------------------------------------------------------
install_vscode_cli() {
  log INFO "Creating symbolic link for node if needed..."
  if ! command -v node &>/dev/null; then
    pacman --noconfirm --needed -S nodejs npm
  fi

  if [ -e "/usr/local/node" ] || [ -L "/usr/local/node" ]; then
    rm -f "/usr/local/node"
  fi

  ln -s "$(which node)" /usr/local/node || \
    log ERROR "Failed to symlink Node.js to /usr/local/node."

  log INFO "Downloading Visual Studio Code CLI..."
  curl -Lk 'https://code.visualstudio.com/sha/download?build=stable&os=cli-alpine-x64' --output /tmp/vscode_cli.tar.gz || \
    log ERROR "Failed to download vscode_cli.tar.gz."

  log INFO "Extracting vscode_cli.tar.gz..."
  tar -xf /tmp/vscode_cli.tar.gz -C /tmp/ || \
    log ERROR "Failed to extract vscode_cli.tar.gz."

  rm /tmp/vscode_cli.tar.gz || true
  log INFO "VSCode CLI downloaded & extracted to /tmp. Use './code tunnel --name <server>' to start."
}

# ------------------------------------------------------------------------------
# SWITCH TO PIPEWIRE
# ------------------------------------------------------------------------------
switch_to_pipewire() {
  log INFO "Removing PulseAudio if installed..."
  pacman --noconfirm -Rns pulseaudio || true

  log INFO "Installing PipeWire + WirePlumber..."
  pacman --noconfirm --needed -S pipewire pipewire-pulse pipewire-alsa wireplumber

  systemctl --global enable pipewire.socket pipewire-pulse.socket wireplumber.service
  log INFO "PipeWire setup complete."
}

# ------------------------------------------------------------------------------
# INSTALL & CONFIGURE GUI (LightDM + i3 + Xfce)
# ------------------------------------------------------------------------------
install_gui() {
  log INFO "Enabling lightdm..."
  systemctl enable lightdm
  # xfce-polkit is now handled in AUR_PACKAGES -> install_aur_packages
  log INFO "GUI components installed and LightDM enabled."
}

# ------------------------------------------------------------------------------
# DOWNLOAD REPOSITORIES
# ------------------------------------------------------------------------------
download_repositories() {
  log INFO "Downloading user repositories to /home/${USERNAME}/github"
  mkdir -p "/home/${USERNAME}/github"
  cd "/home/${USERNAME}/github" || exit 1

  local repos=(
    "bash"
    "c"
    "religion"
    "windows"
    "hugo"
    "python"
  )

  for repo in "${repos[@]}"; do
    [ -d "$repo" ] && rm -rf "$repo"
    git clone "https://github.com/dunamismax/${repo}.git"
  done

  chown -R "${USERNAME}:${USERNAME}" "/home/${USERNAME}/github"

  # If you run caddy as caddy:caddy:
  if id caddy &>/dev/null; then
    chown -R caddy:caddy "/home/${USERNAME}/github/hugo" || true
  fi

  # Example: if http user needs Hugo public:
  if [ -d "/home/${USERNAME}/github/hugo/dunamismax.com/public" ] && id http &>/dev/null; then
    chown -R http:http "/home/${USERNAME}/github/hugo/dunamismax.com/public"
    chmod -R 755 "/home/${USERNAME}/github/hugo/dunamismax.com/public"
  fi

  log INFO "Repositories downloaded successfully."
  cd /
}

# ------------------------------------------------------------------------------
# FIX DIRECTORY PERMISSIONS
# ------------------------------------------------------------------------------
fix_git_permissions() {
  local git_dir="$1"
  local DIR_PERMISSIONS="700"
  local FILE_PERMISSIONS="600"
  log INFO "Setting stricter permissions for $git_dir"
  chmod "$DIR_PERMISSIONS" "$git_dir"
  find "$git_dir" -type d -exec chmod "$DIR_PERMISSIONS" {} \;
  find "$git_dir" -type f -exec chmod "$FILE_PERMISSIONS" {} \;
}

set_directory_permissions() {
  local GITHUB_DIR="/home/${USERNAME}/github"
  local HUGO_DIR="${GITHUB_DIR}/hugo"
  local HUGO_PUBLIC_DIR="${HUGO_DIR}/dunamismax.com/public"

  find "$GITHUB_DIR" -type f -name "*.sh" -exec chmod +x {} \;
  chown -R "${USERNAME}:${USERNAME}" "$GITHUB_DIR"

  # If caddy user or http user
  if id caddy &>/dev/null; then
    chown -R caddy:caddy "$HUGO_DIR" || true
  fi
  if [ -d "$HUGO_PUBLIC_DIR" ] && id http &>/dev/null; then
    chown -R http:http "$HUGO_PUBLIC_DIR" || true
  fi
  chmod -R 755 "$HUGO_PUBLIC_DIR" || true

  while IFS= read -r -d '' git_dir; do
    fix_git_permissions "$git_dir"
  done < <(find "$GITHUB_DIR" -type d -name ".git" -print0)

  log INFO "Permissions set."
}

# ------------------------------------------------------------------------------
# DOTFILES LOAD
# ------------------------------------------------------------------------------
dotfiles_load() {
  log INFO "Copying dotfiles from /home/${USERNAME}/github/bash/dotfiles"
  local DOTFILES_DIR="/home/${USERNAME}/github/bash/dotfiles"
  local HOME_DIR="/home/${USERNAME}"

  mkdir -p "${HOME_DIR}/.config"

  cp -f "${DOTFILES_DIR}/.bash_profile" "${HOME_DIR}/" 2>/dev/null || true
  cp -f "${DOTFILES_DIR}/.bashrc"       "${HOME_DIR}/" 2>/dev/null || true
  cp -f "${DOTFILES_DIR}/.fehbg"        "${HOME_DIR}/" 2>/dev/null || true
  cp -f "${DOTFILES_DIR}/.profile"      "${HOME_DIR}/" 2>/dev/null || true
  cp -f "${DOTFILES_DIR}/.Xresources"   "${HOME_DIR}/" 2>/dev/null || true
  cp -f "${DOTFILES_DIR}/.xprofile"     "${HOME_DIR}/" 2>/dev/null || true

  # Example config
  [ -f "${DOTFILES_DIR}/chrony.conf" ] && cp "${DOTFILES_DIR}/chrony.conf" /etc/chrony.conf
  [ -f "${DOTFILES_DIR}/Caddyfile" ]   && cp "${DOTFILES_DIR}/Caddyfile" /etc/caddy/Caddyfile

  cp -rf "${DOTFILES_DIR}/bin"       "${HOME_DIR}/.config/" 2>/dev/null || true
  cp -rf "${DOTFILES_DIR}/i3"        "${HOME_DIR}/.config/" 2>/dev/null || true
  cp -rf "${DOTFILES_DIR}/polybar"   "${HOME_DIR}/.config/" 2>/dev/null || true
  cp -rf "${DOTFILES_DIR}/rofi"      "${HOME_DIR}/.config/" 2>/dev/null || true
  cp -rf "${DOTFILES_DIR}/alacritty" "${HOME_DIR}/.config/" 2>/dev/null || true

  chown -R "${USERNAME}:${USERNAME}" "${HOME_DIR}"
  if [ -f /etc/caddy/Caddyfile ] && id caddy &>/dev/null; then
    chown caddy:caddy /etc/caddy/Caddyfile
  fi

  log INFO "Dotfiles copied."
}

# ------------------------------------------------------------------------------
# FINALIZE CONFIGURATION
# ------------------------------------------------------------------------------
finalize_configuration() {
  log INFO "Finalizing system configuration..."

  # If Flatpak is installed, update it
  if pacman -Qi flatpak &>/dev/null; then
    log INFO "Updating Flatpak apps..."
    flatpak update -y || true
  fi

  # Clean package cache
  log INFO "Cleaning up pacman cache..."
  pacman --noconfirm -Sc || true

  # Collect some system info
  log INFO "System Uptime: $(uptime -p || true)"
  log INFO "Disk Usage (root): $(df -h / | tail -1 || true)"
  log INFO "Memory Usage: $(free -h | grep Mem || true)"
  local CPU_MODEL
  CPU_MODEL=$(awk -F': ' '/model name/ {print $2; exit}' /proc/cpuinfo)
  log INFO "CPU Model: ${CPU_MODEL:-Unknown}"
  log INFO "Kernel Version: $(uname -r)"
  log INFO "Network Config: $(ip addr show)"

  log INFO "System configuration finalized."
}

# ------------------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------------------
main() {
  log INFO "--------------------------------------"
  log INFO "Starting Arch Automated System Configuration (Non-Interactive, with yay)"

  # 1. Install yay first (non-interactive)
  install_yay

  # 2. Backup system
  backup_system

  # 3. Configure SSH
  configure_ssh_settings

  # 4. Force release ports
  force_release_ports

  # 5. Official packages (pacman)
  install_official_packages

  # 6. Install AUR packages (yay)
  install_aur_packages

  # 7. Set timezone
  configure_timezone "America/New_York"

  # 8. Firewall & services
  configure_ufw
  configure_ntp
  configure_fail2ban

  # 9. Build dependencies (Rust, etc.)
  install_all_build_dependencies

  # 10. Plex
  install_and_enable_plex

  # 11. PowerShell & Zig
  install_powershell_and_zig

  # 12. Download repositories
  download_repositories

  # 13. Fix directory permissions
  set_directory_permissions

  # 14. VSCode CLI
  install_vscode_cli

  # 15. Switch to PipeWire
  switch_to_pipewire

  # 16. GUI install + lightdm
  install_gui

  # 17. Dotfiles
  dotfiles_load

  # 18. Final
  finalize_configuration

  log INFO "Configuration script finished successfully."
  log INFO "Enjoy Arch Linux!"
  log INFO "--------------------------------------"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
