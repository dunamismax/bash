#!/usr/local/bin/bash
set -Eeuo pipefail
IFS=$'\n\t'
trap 'handle_error "Script failed at line $LINENO with exit code $?."' ERR

LOG_FILE="/var/log/freebsd_setup.log"
USERNAME="sawyer"
USER_HOME="/home/${USERNAME}"

mkdir -p "$(dirname "$LOG_FILE")"
touch "$LOG_FILE"
chmod 600 "$LOG_FILE"

log() {
    local level="${1:-INFO}"
    shift
    local message="$*"
    local timestamp
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")
    local RED='\033[0;31m'
    local YELLOW='\033[0;33m'
    local GREEN='\033[0;32m'
    local BLUE='\033[0;34m'
    local NC='\033[0m'
    case "${level^^}" in
        INFO) local color="${GREEN}" ;;
        WARN|WARNING) local color="${YELLOW}"; level="WARN" ;;
        ERROR) local color="${RED}" ;;
        DEBUG) local color="${BLUE}" ;;
        *) local color="${NC}"; level="INFO" ;;
    esac
    local log_entry="[$timestamp] [${level^^}] $message"
    echo "$log_entry" >> "$LOG_FILE"
    printf "${color}%s${NC}\n" "$log_entry" >&2
}

handle_error() {
    local error_message="${1:-An error occurred. Check the log for details.}"
    local exit_code="${2:-1}"
    log ERROR "$error_message (Exit Code: $exit_code)"
    log ERROR "Script failed at line $LINENO in function ${FUNCNAME[1]:-main}."
    echo "ERROR: $error_message (Exit Code: $exit_code)" >&2
    exit "$exit_code"
}

usage() {
    cat <<EOF
Usage: sudo $(basename "$0") [OPTIONS]
This script installs and configures a FreeBSD system with essential packages,
a minimal GUI environment, and dotfiles.
Options:
  -h, --help    Show this help message and exit.
EOF
    exit 0
}

check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        handle_error "Script must be run as root."
    fi
}

check_network() {
    log INFO "Checking network connectivity..."
    if ! ping -c1 -t5 google.com &>/dev/null; then
        log WARN "No network connectivity detected."
    else
        log INFO "Network connectivity OK."
    fi
}

update_system() {
    log INFO "Updating pkg repository..."
    if ! pkg update; then
        log WARN "pkg update encountered issues."
    fi
    log INFO "Upgrading installed packages..."
    if ! pkg upgrade -y; then
        log WARN "pkg upgrade encountered issues."
    fi
}

install_packages() {
    log INFO "Installing essential packages..."
    PACKAGES=(
        bash vim nano zsh screen tmux mc htop tree ncdu neofetch
        git curl wget rsync
        python3 gcc cmake ninja meson go gdb
        xorg gnome gdm alacritty
        nmap lsof iftop iperf3 netcat tcpdump lynis
        john hydra aircrack-ng nikto
        postgresql14-client postgresql14-server mysql80-client mysql80-server redis
        ruby rust
        jq doas
    )
    for pkg in "${PACKAGES[@]}"; do
        if ! pkg install -y "$pkg"; then
            log WARN "Package $pkg failed to install."
        else
            log INFO "Installed package: $pkg"
        fi
    done
}

create_user() {
    if ! id "$USERNAME" &>/dev/null; then
        log INFO "Creating user '$USERNAME'..."
        if ! pw useradd "$USERNAME" -m -s /usr/local/bin/bash -G wheel; then
            log WARN "Failed to create user '$USERNAME'."
        else
            echo "changeme" | pw usermod "$USERNAME" -h 0
            log INFO "User '$USERNAME' created with default password 'changeme'."
        fi
    else
        log INFO "User '$USERNAME' already exists."
    fi
}

configure_timezone() {
    local TIMEZONE="America/New_York"
    log INFO "Setting timezone to $TIMEZONE..."
    if [ -f "/usr/share/zoneinfo/${TIMEZONE}" ]; then
        cp "/usr/share/zoneinfo/${TIMEZONE}" /etc/localtime
        echo "$TIMEZONE" > /etc/timezone
        log INFO "Timezone set to $TIMEZONE."
    else
        log WARN "Timezone file for $TIMEZONE not found."
    fi
}

setup_repos() {
    local repo_dir="${USER_HOME}/github"
    log INFO "Cloning repositories into $repo_dir..."
    mkdir -p "$repo_dir"
    for repo in bash windows web python go misc; do
        local target_dir="$repo_dir/$repo"
        rm -rf "$target_dir"
        if ! git clone "https://github.com/dunamismax/$repo.git" "$target_dir"; then
            log WARN "Failed to clone repository: $repo"
        else
            log INFO "Cloned repository: $repo"
        fi
    done
    chown -R "${USERNAME}:${USERNAME}" "$repo_dir"
}

copy_shell_configs() {
    log INFO "Copying shell configuration files..."
    for file in .bashrc .profile; do
        local src="${USER_HOME}/github/bash/freebsd/dotfiles/$file"
        local dest="${USER_HOME}/$file"
        if [ -f "$src" ]; then
            [ -f "$dest" ] && cp "$dest" "${dest}.bak"
            if ! cp -f "$src" "$dest"; then
                log WARN "Failed to copy $src to $dest."
            else
                chown "${USERNAME}:${USERNAME}" "$dest"
                log INFO "Copied $src to $dest."
            fi
        else
            log WARN "Source file $src not found."
        fi
    done
}

configure_ssh() {
    log INFO "Configuring SSH..."
    if sysrc sshd_enable >/dev/null 2>&1; then
        log INFO "sshd_enable already set."
    else
        sysrc sshd_enable="YES"
        log INFO "sshd_enable set to YES."
    fi
    service sshd restart || log WARN "Failed to restart sshd."
}

secure_ssh_config() {
    local sshd_config="/etc/ssh/sshd_config"
    local backup_file="/etc/ssh/sshd_config.bak"
    if [ -f "$sshd_config" ]; then
        cp "$sshd_config" "$backup_file"
        log INFO "Backed up SSH config to $backup_file."
        sed -i '' 's/^#*PermitRootLogin.*/PermitRootLogin no/' "$sshd_config"
        sed -i '' 's/^#*PasswordAuthentication.*/PasswordAuthentication yes/' "$sshd_config"
        sed -i '' 's/^#*ChallengeResponseAuthentication.*/ChallengeResponseAuthentication no/' "$sshd_config"
        sed -i '' 's/^#*X11Forwarding.*/X11Forwarding no/' "$sshd_config"
        log INFO "SSH configuration hardened."
        service sshd restart || log WARN "Failed to restart sshd after hardening."
    else
        log WARN "SSHD configuration file not found."
    fi
}

install_plex() {
    log INFO "Installing Plex Media Server..."
    if pkg install -y plexmediaserver; then
        log INFO "Plex Media Server installed successfully."
    else
        log WARN "Failed to install Plex Media Server."
    fi
}

configure_zfs() {
    local ZPOOL_NAME="WD_BLACK"
    local MOUNT_POINT="/mnt/${ZPOOL_NAME}"
    log INFO "Configuring ZFS pool..."
    if ! zpool list "$ZPOOL_NAME" &>/dev/null; then
        log INFO "ZFS pool '$ZPOOL_NAME' not found. Skipping import."
    else
        log INFO "ZFS pool '$ZPOOL_NAME' found."
        if zfs set mountpoint="${MOUNT_POINT}" "$ZPOOL_NAME"; then
            log INFO "Mountpoint for pool '$ZPOOL_NAME' set to '$MOUNT_POINT'."
        else
            log WARN "Failed to set mountpoint for $ZPOOL_NAME."
        fi
    fi
}

deploy_user_scripts() {
    local bin_dir="${USER_HOME}/bin"
    local scripts_src="${USER_HOME}/github/bash/freebsd/_scripts/"
    log INFO "Deploying user scripts from $scripts_src to $bin_dir..."
    mkdir -p "$bin_dir"
    if rsync -ah --delete "$scripts_src" "$bin_dir"; then
        find "$bin_dir" -type f -exec chmod 755 {} \;
        log INFO "User scripts deployed successfully."
    else
        log WARN "Failed to deploy user scripts."
    fi
}

setup_cron() {
    log INFO "Starting cron service..."
    service cron start || log WARN "Failed to start cron."
}

configure_periodic() {
    local cron_file="/etc/periodic/daily/freebsd_maintenance"
    log INFO "Configuring daily system maintenance tasks..."
    if [ -f "$cron_file" ]; then
        mv "$cron_file" "${cron_file}.bak.$(date +%Y%m%d%H%M%S)" && \
          log INFO "Existing periodic script backed up." || \
          log WARN "Failed to backup existing periodic script."
    fi
    cat << 'EOF' > "$cron_file"
#!/bin/sh
pkg update -q && pkg upgrade -y && pkg autoremove -y && pkg clean -y
EOF
    if chmod +x "$cron_file"; then
        log INFO "Daily maintenance script created at $cron_file."
    else
        log WARN "Failed to set execute permission on $cron_file."
    fi
}

final_checks() {
    log INFO "Performing final system checks:"
    echo "Kernel: $(uname -r)"
    echo "Uptime: $(uptime)"
    df -h /
    swapinfo -h || true
}

home_permissions() {
    log INFO "Setting ownership and permissions for ${USER_HOME}..."
    chown -R "${USERNAME}:${USERNAME}" "${USER_HOME}"
    find "${USER_HOME}" -type d -exec chmod g+s {} \;
}

install_fastfetch() {
    log INFO "Installing Fastfetch..."
    if pkg install -y fastfetch; then
        log INFO "Fastfetch installed successfully."
    else
        log WARN "Failed to install Fastfetch."
    fi
}

set_bash_shell() {
    if [ "$(id -u)" -ne 0 ]; then
        log WARN "set_bash_shell requires root privileges."
        return 1
    fi
    if [ ! -x /usr/local/bin/bash ]; then
        log INFO "Bash not found. Installing via pkg..."
        pkg install -y bash || { log WARN "Failed to install Bash."; return 1; }
    fi
    if ! grep -Fxq "/usr/local/bin/bash" /etc/shells; then
        echo "/usr/local/bin/bash" >> /etc/shells
        log INFO "Added /usr/local/bin/bash to /etc/shells."
    fi
    chsh -s /usr/local/bin/bash "$USERNAME"
    log INFO "Default shell for $USERNAME changed to /usr/local/bin/bash."
}

enable_gdm() {
    log INFO "Enabling GDM display/login manager service..."
    sysrc gdm_enable="YES"
    if service gdm start; then
        log INFO "GDM service started successfully."
    else
        log WARN "Failed to start GDM service."
    fi
}

install_gui() {
    log INFO "--------------------------------------"
    log INFO "Starting minimal GUI installation..."
    log INFO "Installing required GUI packages..."
    if pkg install -y \
        xorg xinit xauth xrandr xset xsetroot \
        i3 i3status i3lock \
        drm-kmod dmenu feh picom alacritty \
        pulseaudio pavucontrol flameshot clipmenu \
        vlc dunst thunar firefox; then
        log INFO "GUI packages installed successfully."
    else
        handle_error "Failed to install one or more GUI packages."
    fi
    log INFO "Minimal GUI installation completed."
    log INFO "--------------------------------------"
}

setup_dotfiles() {
    log INFO "--------------------------------------"
    log INFO "Starting dotfiles setup..."
    local dotfiles_dir="${USER_HOME}/github/bash/freebsd/dotfiles"
    local config_dir="${USER_HOME}/.config"
    if [[ ! -d "$dotfiles_dir" ]]; then
        handle_error "Dotfiles directory not found: $dotfiles_dir"
    fi
    log INFO "Ensuring configuration directory exists at: $config_dir"
    mkdir -p "$config_dir" || handle_error "Failed to create config directory at $config_dir."
    local files=(
        "${dotfiles_dir}/.xinitrc:${USER_HOME}/"
    )
    local dirs=(
        "${dotfiles_dir}/alacritty:${config_dir}"
        "${dotfiles_dir}/i3:${config_dir}"
        "${dotfiles_dir}/picom:${config_dir}"
        "${dotfiles_dir}/i3status:${config_dir}"
    )
    log INFO "Copying dotfiles (files)..."
    for mapping in "${files[@]}"; do
        local src="${mapping%%:*}"
        local dst="${mapping#*:}"
        if [[ -f "$src" ]]; then
            cp "$src" "$dst" || handle_error "Failed to copy file: $src to $dst"
            log INFO "Copied file: $src -> $dst"
        else
            log WARN "Source file not found, skipping: $src"
        fi
    done
    log INFO "Copying dotfiles (directories)..."
    for mapping in "${dirs[@]}"; do
        local src="${mapping%%:*}"
        local dst="${mapping#*:}"
        if [[ -d "$src" ]]; then
            cp -r "$src" "$dst" || handle_error "Failed to copy directory: $src to $dst"
            log INFO "Copied directory: $src -> $dst"
        else
            log WARN "Source directory not found, skipping: $src"
        fi
    done
    log INFO "Setting ownership for all files under ${USER_HOME}..."
    chown -R "${USERNAME}:${USERNAME}" "${USER_HOME}" || handle_error "Failed to set ownership for ${USER_HOME}."
    log INFO "Dotfiles setup completed successfully."
    log INFO "--------------------------------------"
}

prompt_reboot() {
    read -rp "Reboot now? [y/N]: " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        log INFO "Rebooting system..."
        reboot
    else
        log INFO "Reboot canceled. Please reboot later to apply all changes."
    fi
}

main() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h|--help) usage ;;
            *) log WARN "Unknown option: $1"; usage ;;
        esac
        shift
    done
    check_root
    check_network
    update_system
    install_packages
    create_user
    configure_timezone
    setup_repos
    copy_shell_configs
    configure_ssh
    secure_ssh_config
    install_plex
    configure_zfs
    deploy_user_scripts
    setup_cron
    configure_periodic
    install_fastfetch
    set_bash_shell
    enable_gdm
    install_gui
    setup_dotfiles
    final_checks
    home_permissions
    prompt_reboot
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi