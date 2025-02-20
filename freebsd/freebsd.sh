#!/usr/local/bin/bash
#
# FreeBSD system setup bash script
# :)
#
set -Eeuo pipefail
IFS=$'\n\t'
trap 'handle_error "Script failed at line $LINENO with exit code $?."' ERR

LOG_FILE="/var/log/freebsd_setup.log"
USERNAME="sawyer"
USER_HOME="/home/${USERNAME}"

mkdir -p "$(dirname "$LOG_FILE")"
touch "$LOG_FILE"
chmod 600 "$LOG_FILE"

#--------------------------------------------------
# Basic utility functions (logging, error handling, etc.)
#--------------------------------------------------
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
a minimal GUI environment, dotfiles, and additional setup tasks.
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

#--------------------------------------------------
# New Functions from additional scripts
#--------------------------------------------------

# --- FreeBSD System Backup (from freebsd_backup.sh) ---
freebsd_perform_backup() {
    log INFO "Starting backup and compression to ${DESTINATION}/${BACKUP_NAME}"
    if tar -I pigz -cf "${DESTINATION}/${BACKUP_NAME}" "${EXCLUDES_ARGS[@]}" -C / .; then
        log INFO "Backup and compression completed: ${DESTINATION}/${BACKUP_NAME}"
    else
        handle_error "Backup process failed."
    fi
}

freebsd_cleanup_backups() {
    log INFO "Removing backups in ${DESTINATION} older than ${RETENTION_DAYS} days"
    if find "$DESTINATION" -mindepth 1 -maxdepth 1 -type f -mtime +$RETENTION_DAYS -delete; then
        log INFO "Old backups removed."
    else
        log WARN "Failed to remove some old backups."
    fi
}

backup_freebsd_system() {
    # Define backup parameters (customize as needed)
    SOURCE="/"
    DESTINATION="/mnt/WD_BLACK/BACKUP/freebsd-backups"
    RETENTION_DAYS=7
    TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
    BACKUP_NAME="backup-${TIMESTAMP}.tar.gz"
    # Build exclusion args
    EXCLUDES=( "./proc/*" "./sys/*" "./dev/*" "./run/*" "./tmp/*" "./mnt/*" "./media/*" "./swapfile" "./lost+found" "./var/tmp/*" "./var/cache/*" "./var/log/*" "*.iso" "*.tmp" "*.swap.img" )
    EXCLUDES_ARGS=()
    for EXCLUDE in "${EXCLUDES[@]}"; do
        EXCLUDES_ARGS+=(--exclude="$EXCLUDE")
    done

    freebsd_perform_backup
    freebsd_cleanup_backups
}

# --- Plex Backup (from plex_backup.sh) ---
plex_perform_backup() {
    log INFO "Starting on-the-fly Plex backup and compression to ${DESTINATION}/${BACKUP_NAME}"
    if tar -I pigz --one-file-system -cf "${DESTINATION}/${BACKUP_NAME}" -C "$SOURCE" .; then
        log INFO "Plex backup and compression completed: ${DESTINATION}/${BACKUP_NAME}"
    else
        handle_error "Plex backup process failed."
    fi
}

plex_cleanup_backups() {
    log INFO "Removing Plex backups older than ${RETENTION_DAYS} days from ${DESTINATION}"
    if find "$DESTINATION" -mindepth 1 -maxdepth 1 -type f -mtime +$RETENTION_DAYS -delete; then
        log INFO "Old Plex backups removed."
    else
        log WARN "Failed to remove some old Plex backups."
    fi
}

backup_plex_data() {
    # Define Plex backup parameters (customize as needed)
    SOURCE="/usr/local/plexdata/Library/Application Support/Plex Media Server/"
    DESTINATION="/mnt/WD_BLACK/BACKUP/plex-backups"
    RETENTION_DAYS=7
    TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
    BACKUP_NAME="plex-backup-${TIMESTAMP}.tar.gz"

    # Ensure source exists and destination is mounted
    if [[ ! -d "$SOURCE" ]]; then
        handle_error "Plex source directory '$SOURCE' does not exist."
    fi
    mkdir -p "$DESTINATION" || handle_error "Failed to create destination directory: $DESTINATION"
    if ! mount | grep -q "$DESTINATION"; then
        handle_error "Destination mount point for '$DESTINATION' is not available."
    fi

    plex_perform_backup
    plex_cleanup_backups
}

# --- FiraCode Nerd Font Installer (from install_firacode_nerd_font.sh) ---
install_firacode_nerd_font() {
    local font_url="https://github.com/ryanoasis/nerd-fonts/raw/master/patched-fonts/FiraCode/Regular/FiraCodeNerdFont-Regular.ttf"
    local font_dir="/usr/local/share/fonts/nerd-fonts"
    local font_file="FiraCodeNerdFont-Regular.ttf"

    log INFO "Starting FiraCode Nerd Font installation..."
    if [[ ! -d "$font_dir" ]]; then
        log INFO "Creating font directory: $font_dir"
        mkdir -p "$font_dir" || handle_error "Failed to create font directory: $font_dir"
    fi
    chmod 755 "$font_dir" || handle_error "Failed to set permissions for the font directory."
    log INFO "Downloading font from $font_url..."
    curl -L -o "$font_dir/$font_file" "$font_url" || handle_error "Failed to download font from $font_url."
    log INFO "Font downloaded successfully."
    if [[ ! -f "$font_dir/$font_file" ]]; then
        handle_error "Font file not found after download: $font_dir/$font_file"
    fi
    chmod 644 "$font_dir/$font_file" || handle_error "Failed to set permissions for the font file."
    chown root:wheel "$font_dir/$font_file" || handle_error "Failed to set ownership for the font file."
    fc-cache -fv >/dev/null 2>&1 || handle_error "Failed to refresh font cache."
    log INFO "FiraCode Nerd Font installation completed successfully."
}

# --- Firewall Setup (from FreeBSD Firewall Setup Script) ---
backup_pf_conf() {
    local pf_conf="/etc/pf.conf"
    if [ -f "$pf_conf" ]; then
        local backup="/etc/pf.conf.backup.$(date +%Y%m%d%H%M%S)"
        cp "$pf_conf" "$backup"
        log INFO "Existing pf.conf backed up to $backup"
    else
        log INFO "No existing /etc/pf.conf found. Continuing."
    fi
}

detect_ext_if() {
    local iface
    iface=$(route -n get default 2>/dev/null | awk '/interface:/{print $2}')
    if [ -z "$iface" ]; then
        log ERROR "Could not determine the external interface. Please set it manually."
        exit 1
    fi
    echo "$iface"
}

generate_pf_conf() {
    local ext_if="$1"
    local pf_conf="/etc/pf.conf"
    log INFO "Generating new $pf_conf with external interface: $ext_if"
    cat <<EOF > "$pf_conf"
#
# pf.conf generated by firewall_setup.sh on $(date)
#
ext_if = "$ext_if"
set skip on lo
scrub in all
block in all
pass out all keep state
pass in on \$ext_if proto tcp from any to (\$ext_if) port { 22, 80, 443 } flags S/SA keep state
pass in on \$ext_if proto tcp from any to (\$ext_if) port 32400 keep state
pass in on \$ext_if proto udp from any to (\$ext_if) port { 1900, 32410, 32412, 32413, 32414 } keep state
EOF
    log INFO "New pf.conf generated."
}

enable_and_reload_pf() {
    if ! sysrc -n pf_enable 2>/dev/null | grep -q "YES"; then
        sysrc pf_enable="YES"
        log INFO "Set pf_enable to YES in rc.conf."
    fi
    if ! service pf status >/dev/null 2>&1; then
        service pf start
        log INFO "PF service started."
    else
        pfctl -f /etc/pf.conf && log INFO "PF configuration reloaded successfully."
    fi
}

configure_firewall() {
    check_root
    backup_pf_conf
    local ext_if
    ext_if=$(detect_ext_if)
    generate_pf_conf "$ext_if"
    enable_and_reload_pf
    log INFO "Firewall configuration complete."
}

# --- Python Development Environment Setup (from python-dev-setup.sh) ---
install_pkg_dependencies() {
    log INFO "Updating pkg caches..."
    pkg update -f
    log INFO "Upgrading existing packages..."
    pkg upgrade -y
    log INFO "Installing pkg-based dependencies..."
    pkg install -y git curl wget vim tmux unzip zip ca_root_nss libffi readline sqlite3 ncurses xz llvm gmake python3 py39-pip
    log INFO "Cleaning up pkg cache..."
    pkg clean -y
}

install_or_update_pyenv() {
    if [[ ! -d "${HOME}/.pyenv" ]]; then
        log INFO "Installing pyenv..."
        git clone https://github.com/pyenv/pyenv.git "${HOME}/.pyenv"
        if ! grep -q 'export PYENV_ROOT' "${HOME}/.bashrc"; then
            cat <<'EOF' >> "${HOME}/.bashrc"

# >>> pyenv initialization >>>
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
if command -v pyenv 1>/dev/null 2>&1; then
    eval "$(pyenv init -)"
fi
# <<< pyenv initialization <<<
EOF
        fi
    else
        log INFO "Updating pyenv..."
        pushd "${HOME}/.pyenv" >/dev/null
        git pull --ff-only
        popd >/dev/null
    fi
    export PYENV_ROOT="$HOME/.pyenv"
    export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init -)"
}

install_latest_python() {
    log INFO "Finding the latest stable Python 3.x version via pyenv..."
    LATEST_PY3="$(pyenv install -l | awk '/^[[:space:]]*3\.[0-9]+\.[0-9]+$/{latest=$1}END{print latest}')"
    if [[ -z "$LATEST_PY3" ]]; then
        handle_error "Could not determine the latest Python 3.x version from pyenv."
    fi
    CURRENT_PY3="$(pyenv global || true)"
    log INFO "Latest Python 3.x version is $LATEST_PY3"
    log INFO "Currently active pyenv Python is $CURRENT_PY3"
    INSTALL_NEW_PYTHON=false
    if [[ "$CURRENT_PY3" != "$LATEST_PY3" ]]; then
        if ! pyenv versions --bare | grep -q "^${LATEST_PY3}\$"; then
            log INFO "Installing Python $LATEST_PY3 via pyenv..."
            pyenv install "$LATEST_PY3"
        fi
        log INFO "Setting Python $LATEST_PY3 as global..."
        pyenv global "$LATEST_PY3"
        INSTALL_NEW_PYTHON=true
    else
        log INFO "Python $LATEST_PY3 is already installed and set as global."
    fi
    eval "$(pyenv init -)"
    if $INSTALL_NEW_PYTHON; then
        return 0
    else
        return 1
    fi
}

install_or_upgrade_pipx_and_tools() {
    if ! command -v pipx >/dev/null 2>&1; then
        log INFO "Installing pipx with current Python version."
        python -m pip install --upgrade pip
        python -m pip install --user pipx
    fi
    if ! grep -q 'export PATH=.*\.local/bin' "${HOME}/.bashrc"; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "${HOME}/.bashrc"
    fi
    export PATH="$HOME/.local/bin:$PATH"
    pipx upgrade pipx || true
    PIPX_TOOLS=( ansible-core black cookiecutter coverage flake8 isort ipython mypy pip-tools pylint pyupgrade pytest rich-cli tldr tox twine yt-dlp poetry pre-commit )
    if [[ "${1:-false}" == "true" ]]; then
        log INFO "Python version changed; performing pipx reinstall-all to avoid breakage..."
        pipx reinstall-all
    else
        log INFO "Upgrading all pipx packages to ensure they’re current..."
        pipx upgrade-all || true
    fi
    log INFO "Ensuring each tool in PIPX_TOOLS is installed/upgraded..."
    for tool in "${PIPX_TOOLS[@]}"; do
        if pipx list | grep -q "$tool"; then
            pipx upgrade "$tool" || true
        else
            pipx install "$tool" || true
        fi
    done
}

setup_python_dev() {
    install_pkg_dependencies
    install_or_update_pyenv
    if install_latest_python; then
        install_or_upgrade_pipx_and_tools "true"
    else
        install_or_upgrade_pipx_and_tools "false"
    fi
    log INFO "Python development environment setup complete."
}

# --- Sudo Setup (from FreeBSD Sudo Setup Script) ---
install_sudo() {
    if ! command -v sudo &>/dev/null; then
        log INFO "sudo not found. Installing sudo..."
        pkg update && pkg install sudo || { log ERROR "Failed to install sudo via pkg."; exit 1; }
        log INFO "sudo installed successfully."
    else
        log INFO "sudo is already installed."
    fi
}

backup_sudoers() {
    local sudoers_file="/usr/local/etc/sudoers"
    if [ -f "$sudoers_file" ]; then
        local backup="/usr/local/etc/sudoers.backup.$(date +%Y%m%d%H%M%S)"
        cp "$sudoers_file" "$backup"
        log INFO "Backed up existing sudoers file to $backup."
    else
        log WARN "sudoers file not found at /usr/local/etc/sudoers. A new one will be created."
    fi
}

configure_sudoers() {
    local sudoers_file="/usr/local/etc/sudoers"
    local entry="sawyer ALL=(ALL) ALL"
    if grep -q "^${entry}$" "$sudoers_file" 2>/dev/null; then
        log INFO "User 'sawyer' is already configured in sudoers."
    else
        log INFO "Adding 'sawyer' to the sudoers file."
        echo "$entry" >> "$sudoers_file"
        if visudo -c -f "$sudoers_file" &>/dev/null; then
            log INFO "sudoers file syntax is valid."
        else
            log ERROR "sudoers file syntax error. Restoring backup and exiting."
            backup_file=$(ls -t /usr/local/etc/sudoers.backup.* 2>/dev/null | head -n1)
            if [ -n "$backup_file" ]; then
                cp "$backup_file" "$sudoers_file"
                log INFO "Restored sudoers from backup $backup_file."
            fi
            exit 1
        fi
    fi
}

setup_sudo() {
    install_sudo
    backup_sudoers
    configure_sudoers
    log INFO "Sudo installation and configuration complete."
}

# --- ZFS Pool Configuration (from configure_zfs_freebsd.sh) ---
configure_zfs_pool() {
    local ZPOOL_NAME="WD_BLACK"
    local MOUNT_POINT="/mnt/${ZPOOL_NAME}"
    log INFO "Configuring WD External ZFS Pool on FreeBSD"
    if [[ ! -d "$MOUNT_POINT" ]]; then
        log INFO "Creating mount point directory: $MOUNT_POINT"
        mkdir -p "$MOUNT_POINT" || handle_error "Failed to create mount point directory: $MOUNT_POINT"
    fi
    if ! zpool list "$ZPOOL_NAME" >/dev/null 2>&1; then
        log INFO "Importing ZFS pool '$ZPOOL_NAME'..."
        if ! zpool import -f "$ZPOOL_NAME"; then
            handle_error "Failed to import ZFS pool '$ZPOOL_NAME'."
        fi
    else
        log INFO "ZFS pool '$ZPOOL_NAME' is already imported."
    fi
    local current_mountpoint
    current_mountpoint=$(zfs get -H -o value mountpoint "$ZPOOL_NAME")
    if [[ "$current_mountpoint" != "$MOUNT_POINT" ]]; then
        log INFO "Setting mountpoint for pool '$ZPOOL_NAME' to '$MOUNT_POINT'..."
        if ! zfs set mountpoint="$MOUNT_POINT" "$ZPOOL_NAME"; then
            handle_error "Failed to set mountpoint for ZFS pool '$ZPOOL_NAME'."
        fi
    else
        log INFO "Mountpoint for pool '$ZPOOL_NAME' is already set to '$MOUNT_POINT'."
    fi
    if ! mount | grep -q "on ${MOUNT_POINT} "; then
        log INFO "Mounting ZFS pool '$ZPOOL_NAME'..."
        if ! zfs mount "$ZPOOL_NAME"; then
            handle_error "Failed to mount ZFS pool '$ZPOOL_NAME'."
        fi
    else
        log INFO "ZFS pool '$ZPOOL_NAME' is already mounted on '$MOUNT_POINT'."
    fi
    if ! grep -q '^zfs_enable="YES"' /etc/rc.conf; then
        log WARN "zfs_enable is not set to YES in /etc/rc.conf. Auto-mounting at boot may not work."
        log INFO "To enable auto-mounting, add the following line to /etc/rc.conf:"
        log INFO '  zfs_enable="YES"'
    else
        log INFO "Auto-mounting is enabled in /etc/rc.conf."
    fi
    log INFO "WD External ZFS Pool configuration completed successfully."
}

#--------------------------------------------------
# Remaining original functions
#--------------------------------------------------
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

#--------------------------------------------------
# Main Entry Point
#--------------------------------------------------
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

    # New steps from additional functions:
    configure_firewall
    install_firacode_nerd_font
    backup_freebsd_system
    backup_plex_data
    setup_python_dev
    setup_sudo
    configure_zfs_pool

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