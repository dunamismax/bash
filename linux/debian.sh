#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Script Name: debian_setup.sh
# Description: Automated Debian setup and hardening script with robust error
#              handling and improved logging. This script configures system
#              updates, user setup, firewall rules, SSH hardening, package
#              installation, and additional services.
# Author: Your Name | License: MIT
# Version: 2.1
# ------------------------------------------------------------------------------
#
# Usage:
#   sudo ./debian_setup.sh
#
# Notes:
#   - This script must be run as root.
#   - Log output is saved to /var/log/debian_setup.log.
#
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# ENABLE STRICT MODE
# ------------------------------------------------------------------------------
set -Eeuo pipefail

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES & CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE="/var/log/debian_setup.log"
USERNAME="sawyer"

# List of essential packages to be installed.
PACKAGES=(
    bash zsh fish vim nano emacs mc neovim screen tmux
    gcc make cmake meson intltool gettext pigz libtool pkg-config bzip2 git
    chrony sudo bash-completion logrotate
    curl wget tcpdump rsync nmap lynx dnsutils mtr netcat-openbsd socat
    htop tig jq vnstat tree fzf smartmontools lsof
    gdisk ntfs-3g ncdu unzip zip
    patch gawk expect
    fd-find bat ripgrep hyperfine
    ffmpeg restic mpv nnn newsboat irssi
    taskwarrior cowsay figlet
    ufw fail2ban
    aircrack-ng reaver hydra john sqlmap gobuster dirb wfuzz
    netdiscover arp-scan
    ettercap-text-only tshark hashcat recon-ng crunch iotop iftop
    sysstat traceroute
    whois strace ltrace iperf3 binwalk
    foremost steghide hashid
)

# ------------------------------------------------------------------------------
# COLOR CONSTANTS (Nord theme; 24‑bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0='\033[38;2;46;52;64m'      # Dark background color
NORD1='\033[38;2;59;66;82m'
NORD2='\033[38;2;67;76;94m'
NORD3='\033[38;2;76;86;106m'
NORD4='\033[38;2;216;222;233m'
NORD5='\033[38;2;229;233;240m'
NORD6='\033[38;2;236;239;244m'
NORD7='\033[38;2;143;188;187m'
NORD8='\033[38;2;136;192;208m'
NORD9='\033[38;2;129;161;193m'   # Bluish for DEBUG messages
NORD10='\033[38;2;94;129;172m'
NORD11='\033[38;2;191;97;106m'   # Reddish for ERROR messages
NORD12='\033[38;2;208;135;112m'
NORD13='\033[38;2;235;203;139m'  # Yellowish for WARN messages
NORD14='\033[38;2;163;190;140m'  # Greenish for INFO messages
NC='\033[0m'                    # No Color

# ------------------------------------------------------------------------------
# LOGGING FUNCTIONS
# ------------------------------------------------------------------------------
# log <LEVEL> <message>
# Logs the provided message with a timestamp and level both to the log file
# and (if outputting to a terminal) to stderr with a themed color.
log() {
    local level="${1:-INFO}"
    shift
    local message="$*"
    local timestamp
    timestamp="$(date +"%Y-%m-%d %H:%M:%S")"
    local log_entry="[$timestamp] [${level^^}] $message"

    # Append the log entry to the log file.
    echo "$log_entry" >> "$LOG_FILE"

    # If stderr is a terminal, add color.
    if [ -t 2 ]; then
        case "${level^^}" in
            INFO)  printf "%b%s%b\n" "$NORD14" "$log_entry" "$NC" ;;
            WARN)  printf "%b%s%b\n" "$NORD13" "$log_entry" "$NC" ;;
            ERROR) printf "%b%s%b\n" "$NORD11" "$log_entry" "$NC" ;;
            DEBUG) printf "%b%s%b\n" "$NORD9"  "$log_entry" "$NC" ;;
            *)     printf "%s\n" "$log_entry" ;;
        esac
    else
        echo "$log_entry" >&2
    fi
}

log_info()  { log INFO "$@"; }
log_warn()  { log WARN "$@"; }
log_error() { log ERROR "$@"; }
log_debug() { log DEBUG "$@"; }

# handle_error <error_message> [exit_code]
# Logs an error message and terminates the script with the provided exit code.
handle_error() {
    local error_message="${1:-"An unknown error occurred."}"
    local exit_code="${2:-1}"
    log_error "$error_message (Exit Code: $exit_code)"
    log_error "Error encountered at line $LINENO in function ${FUNCNAME[1]:-main}."
    echo -e "${NORD11}ERROR: $error_message (Exit Code: $exit_code)${NC}" >&2
    exit "$exit_code"
}

# cleanup
# This function is executed upon script exit to perform any necessary cleanup.
cleanup() {
    log_info "Performing cleanup tasks before exit."
    # Insert any necessary cleanup commands here.
}

trap cleanup EXIT
trap 'handle_error "An unexpected error occurred at line $LINENO."' ERR

# ------------------------------------------------------------------------------
# UTILITY FUNCTIONS
# ------------------------------------------------------------------------------

# print_section <title>
# Logs a formatted section header.
print_section() {
    local title="$1"
    local border
    border=$(printf '─%.0s' {1..60})
    log_info "${NORD10}${border}${NC}"
    log_info "${NORD10}  $title${NC}"
    log_info "${NORD10}${border}${NC}"
}

# check_root
# Exits with an error if the script is not executed as root.
check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        handle_error "Script must be run as root. Exiting."
    fi
}

# check_network
# Tests network connectivity by pinging a well-known host.
check_network() {
    print_section "Network Connectivity Check"
    log_info "Verifying network connectivity..."
    if ! ping -c 1 -W 5 google.com >/dev/null 2>&1; then
        handle_error "No network connectivity. Please verify your network settings."
    fi
    log_info "Network connectivity verified."
}

# update_system
# Updates package repository information and upgrades installed packages.
update_system() {
    print_section "System Update & Upgrade"
    log_info "Updating package repositories..."
    if ! apt-get update -qq; then
        handle_error "Failed to update package repositories."
    fi

    log_info "Upgrading system packages..."
    if ! apt-get upgrade -y; then
        handle_error "Failed to upgrade packages."
    fi

    log_info "System update and upgrade complete."
}

# ensure_user
# Creates the specified user if it does not already exist.
ensure_user() {
    print_section "User Setup"
    if id -u "$USERNAME" >/dev/null 2>&1; then
        log_info "User '$USERNAME' already exists."
    else
        log_info "Creating user '$USERNAME'..."
        if ! useradd -m -s /bin/bash "$USERNAME"; then
            handle_error "Failed to create user '$USERNAME'."
        fi
        # Lock the password to prevent direct login.
        if ! passwd -l "$USERNAME" >/dev/null 2>&1; then
            log_warn "Failed to lock password for user '$USERNAME'."
        fi
        log_info "User '$USERNAME' created successfully."
    fi
}

# configure_sudoers
# Ensures that the specified user has sudo privileges.
configure_sudoers() {
    print_section "Sudoers Configuration"
    local SUDOERS_FILE="/etc/sudoers"

    # Backup the sudoers file if a backup does not already exist.
    if [ ! -f "${SUDOERS_FILE}.bak" ]; then
        cp "$SUDOERS_FILE" "${SUDOERS_FILE}.bak" || log_warn "Unable to create backup of sudoers file."
        log_info "Backup of sudoers file created at ${SUDOERS_FILE}.bak"
    fi

    # Append the sudoers entry for the user if it does not already exist.
    if grep -Eq "^[[:space:]]*${USERNAME}[[:space:]]+ALL=\(ALL\)[[:space:]]+ALL" "$SUDOERS_FILE"; then
        log_info "Sudoers entry for '$USERNAME' already exists."
    else
        echo "${USERNAME} ALL=(ALL) ALL" >> "$SUDOERS_FILE" || log_warn "Failed to append sudoers entry for '$USERNAME'."
        log_info "Added sudoers entry for '$USERNAME'."
    fi

    log_info "Sudoers configuration complete."
}

# install_packages
# Installs a list of essential system packages.
install_packages() {
    print_section "Essential Package Installation"
    log_info "Installing packages..."
    if ! apt-get install -y "${PACKAGES[@]}"; then
        handle_error "Failed to install one or more packages."
    fi
    log_info "Package installation complete."
}

# configure_ssh
# Hardens the SSH server by disabling root login and password authentication.
configure_ssh() {
    print_section "SSH Hardening"
    log_info "Configuring SSH server..."
    local SSH_CONFIG="/etc/ssh/sshd_config"
    if [ -f "$SSH_CONFIG" ]; then
        cp "$SSH_CONFIG" "${SSH_CONFIG}.bak"
        log_info "Backup of SSH config saved as ${SSH_CONFIG}.bak"
        sed -i -e 's/^#\?PermitRootLogin.*/PermitRootLogin no/' \
               -e 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' \
               -e 's/^#\?PermitEmptyPasswords.*/PermitEmptyPasswords no/' "$SSH_CONFIG"
        if ! systemctl restart ssh; then
            handle_error "Failed to restart SSH service."
        fi
        log_info "SSH configuration updated and service restarted."
    else
        log_warn "SSH configuration file not found at $SSH_CONFIG."
    fi
}

# configure_firewall
# Configures the Uncomplicated Firewall (ufw) with default rules and enables it.
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
    "$ufw_cmd" allow 32400/tcp || log_warn "Failed to allow Plex Media Server port"
    "$ufw_cmd" --force enable || handle_error "Failed to enable ufw firewall"
    systemctl enable ufw || log_warn "Failed to enable ufw service"
    systemctl start ufw || log_warn "Failed to start ufw service"
    log_info "Firewall configured and enabled."
}

# configure_fail2ban
# Enables and starts the fail2ban service for intrusion prevention.
configure_fail2ban() {
    print_section "fail2ban Configuration"
    log_info "Enabling fail2ban service..."
    if ! systemctl enable fail2ban; then
        log_warn "Failed to enable fail2ban service."
    fi
    if ! systemctl start fail2ban; then
        log_warn "Failed to start fail2ban service."
    else
        log_info "fail2ban service started successfully."
    fi
}

# install_plex
# Downloads and installs the Plex Media Server package, then configures it to
# run under the specified user account.
install_plex() {
    print_section "Plex Media Server Installation"
    log_info "Ensuring required system utilities are available..."
    export PATH="$PATH:/sbin:/usr/sbin"
    if ! command -v ldconfig >/dev/null; then
        handle_error "ldconfig command not found. Please install libc-bin or fix your PATH."
    fi
    if ! command -v start-stop-daemon >/dev/null; then
        handle_error "start-stop-daemon command not found. Please install dpkg or fix your PATH."
    fi
    log_info "Downloading Plex Media Server deb file..."
    local plex_deb="/tmp/plexmediaserver.deb"
    local plex_url="https://downloads.plex.tv/plex-media-server-new/1.41.3.9314-a0bfb8370/debian/plexmediaserver_1.41.3.9314-a0bfb8370_amd64.deb"
    if ! wget -q -O "$plex_deb" "$plex_url"; then
        handle_error "Failed to download Plex Media Server deb file."
    fi
    log_info "Installing Plex Media Server from deb file..."
    if ! dpkg -i "$plex_deb"; then
        log_warn "dpkg installation encountered errors, attempting to fix dependencies..."
        if ! apt-get install -f -y; then
            handle_error "Failed to install Plex Media Server due to unresolved dependencies."
        fi
    fi
    local PLEX_CONF="/etc/default/plexmediaserver"
    if [ -f "$PLEX_CONF" ]; then
        sed -i "s/^PLEX_MEDIA_SERVER_USER=.*/PLEX_MEDIA_SERVER_USER=${USERNAME}/" "$PLEX_CONF" \
            || log_warn "Failed to set Plex user in $PLEX_CONF"
    else
        echo "PLEX_MEDIA_SERVER_USER=${USERNAME}" > "$PLEX_CONF" \
            || log_warn "Failed to create $PLEX_CONF"
    fi
    if ! systemctl enable plexmediaserver; then
        log_warn "Failed to enable Plex Media Server service."
    fi
    if ! systemctl start plexmediaserver; then
        log_warn "Plex Media Server failed to start."
    else
        log_info "Plex Media Server installed and started."
    fi
}

# caddy_config
# Downloads and installs Caddy and enables service
caddy_config() {
    print_section "Caddy Configuration"

    # ---------------------------------------------------------------------------
    # Step 1: Release occupied network ports.
    # ---------------------------------------------------------------------------
    log_info "Starting port release process for Caddy installation..."
    release_ports

    # ---------------------------------------------------------------------------
    # Step 2: Install required dependencies and add the Caddy repository.
    # ---------------------------------------------------------------------------
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

    # ---------------------------------------------------------------------------
    # Step 3: Update package lists and install Caddy.
    # ---------------------------------------------------------------------------
    log_info "Updating package lists..."
    apt update || handle_error "Failed to update package lists."

    log_info "Installing Caddy..."
    apt install -y caddy || handle_error "Failed to install Caddy."

    log_info "Caddy installed successfully."

    # ---------------------------------------------------------------------------
    # Step 4: Copy custom Caddyfile.
    # ---------------------------------------------------------------------------
    local CUSTOM_CADDYFILE="/home/sawyer/github/linux/dotfiles/Caddyfile"
    local DEST_CADDYFILE="/etc/caddy/Caddyfile"
    if [ -f "$CUSTOM_CADDYFILE" ]; then
        log_info "Copying custom Caddyfile from $CUSTOM_CADDYFILE to $DEST_CADDYFILE..."
        cp -f "$CUSTOM_CADDYFILE" "$DEST_CADDYFILE" || log_warn "Failed to copy custom Caddyfile."
    else
        log_warn "Custom Caddyfile not found at $CUSTOM_CADDYFILE"
    fi

    # ---------------------------------------------------------------------------
    # Step 5: Enable and start (restart) the Caddy service.
    # ---------------------------------------------------------------------------
    log_info "Enabling Caddy service..."
    systemctl enable caddy || log_warn "Failed to enable Caddy service."

    log_info "Restarting Caddy service to apply new configuration..."
    systemctl restart caddy || log_warn "Failed to restart Caddy service."

    log_info "Caddy configuration completed successfully."
}

# configure_zfs
# Imports a ZFS pool (if not already imported) and sets its mountpoint.
configure_zfs() {
    print_section "ZFS Configuration"
    local ZPOOL_NAME="WD_BLACK"
    if ! zpool list "$ZPOOL_NAME" >/dev/null 2>&1; then
        log_info "Importing ZFS pool '$ZPOOL_NAME'..."
        if ! zpool import "$ZPOOL_NAME"; then
            handle_error "Failed to import ZFS pool '$ZPOOL_NAME'."
        fi
    fi

    if ! zfs set mountpoint=/media/"$ZPOOL_NAME" "$ZPOOL_NAME"; then
        log_warn "Failed to set mountpoint for ZFS pool '$ZPOOL_NAME'."
    else
        log_info "ZFS pool '$ZPOOL_NAME' mountpoint set to /media/$ZPOOL_NAME."
    fi
}

# setup_repos
# Clones several GitHub repositories into a dedicated directory in the user's
# home folder.
setup_repos() {
    print_section "GitHub Repositories Setup"
    log_info "Setting up GitHub repositories for user '$USERNAME'..."
    local GH_DIR="/home/$USERNAME/github"
    if ! mkdir -p "$GH_DIR"; then
        handle_error "Failed to create GitHub directory at $GH_DIR."
    fi

    for repo in bash windows web python go misc; do
        local REPO_DIR="$GH_DIR/$repo"
        if [ -d "$REPO_DIR" ]; then
            log_info "Removing existing directory for repository '$repo'."
            rm -rf "$REPO_DIR"
        fi
        if ! git clone "https://github.com/dunamismax/$repo.git" "$REPO_DIR"; then
            log_warn "Failed to clone repository '$repo'."
        else
            chown -R "$USERNAME:$USERNAME" "$REPO_DIR"
            log_info "Repository '$repo' cloned successfully."
        fi
    done
}

# enable_dunamismax_services
# Creates and enables and starts the systemsd service files for FastAPI website
enable_dunamismax_services() {
    print_section "DunamisMax Services Setup"
    log_info "Enabling DunamisMax website services..."

    # DunamisMax AI Agents Service
    cat <<EOF >/etc/systemd/system/dunamismax-ai-agents.service
[Unit]
Description=DunamisMax AI Agents Service
After=network.target

[Service]
User=${USERNAME}
Group=${USERNAME}
WorkingDirectory=/home/${USERNAME}/github/web/ai_agents
Environment="PATH=/home/${USERNAME}/github/web/ai_agents/.venv/bin"
EnvironmentFile=/home/${USERNAME}/github/web/ai_agents/.env
ExecStart=/home/${USERNAME}/github/web/ai_agents/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8200
Restart=always

[Install]
WantedBy=multi-user.target
EOF

    # DunamisMax File Converter Service
    cat <<EOF >/etc/systemd/system/dunamismax-files.service
[Unit]
Description=DunamisMax File Converter Service
After=network.target

[Service]
User=${USERNAME}
Group=${USERNAME}
WorkingDirectory=/home/${USERNAME}/github/web/converter_service
Environment="PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/home/${USERNAME}/github/web/converter_service/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8300
Restart=always

[Install]
WantedBy=multi-user.target
EOF

    # DunamisMax Messenger Service
    cat <<EOF >/etc/systemd/system/dunamismax-messenger.service
[Unit]
Description=DunamisMax Messenger
After=network.target

[Service]
User=${USERNAME}
Group=${USERNAME}
WorkingDirectory=/home/${USERNAME}/github/web/messenger
Environment="PATH=/home/${USERNAME}/github/web/messenger/.venv/bin"
ExecStart=/home/${USERNAME}/github/web/messenger/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8100
Restart=always

[Install]
WantedBy=multi-user.target
EOF

    # DunamisMax Notes Service
    cat <<EOF >/etc/systemd/system/dunamismax-notes.service
[Unit]
Description=DunamisMax Notes Page
After=network.target

[Service]
User=${USERNAME}
Group=${USERNAME}
WorkingDirectory=/home/${USERNAME}/github/web/notes
Environment="PATH=/home/${USERNAME}/github/web/notes/.venv/bin"
ExecStart=/home/${USERNAME}/github/web/notes/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8500
Restart=always

[Install]
WantedBy=multi-user.target
EOF

    # DunamisMax Main Website Service
    cat <<EOF >/etc/systemd/system/dunamismax.service
[Unit]
Description=DunamisMax Main Website
After=network.target

[Service]
User=${USERNAME}
Group=${USERNAME}
WorkingDirectory=/home/${USERNAME}/github/web/dunamismax
Environment="PATH=/home/${USERNAME}/github/web/dunamismax/.venv/bin"
ExecStart=/home/${USERNAME}/github/web/dunamismax/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF

    # Reload systemd configuration and enable the services
    systemctl daemon-reload
    systemctl enable dunamismax-ai-agents.service
    systemctl enable dunamismax-files.service
    systemctl enable dunamismax-messenger.service
    systemctl enable dunamismax-notes.service
    systemctl enable dunamismax.service

    log_info "DunamisMax services enabled."
}

# docker_config
# Installs and enables Docker and Docker Compose
docker_config() {
    print_section "Docker Configuration"
    log_info "Starting Docker installation and configuration..."

    # -------------------------------
    # Install Docker (using apt-get)
    # -------------------------------
    if command -v docker &>/dev/null; then
        log_info "Docker is already installed."
    else
        log_info "Docker is not installed. Installing Docker..."
        apt-get update || handle_error "Failed to update package lists."
        apt-get install -y docker.io || handle_error "Failed to install Docker."
        log_info "Docker installed successfully."
    fi

    # Add the user to the docker group
    usermod -aG docker "$USERNAME" || log_warn "Failed to add $USERNAME to the docker group."

    # Create or update Docker daemon configuration
    mkdir -p /etc/docker || handle_error "Failed to create /etc/docker directory."
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

    # Enable and restart the Docker service
    systemctl enable docker || log_warn "Could not enable Docker service."
    systemctl restart docker || handle_error "Failed to restart Docker."
    log_info "Docker configuration completed."

    # -------------------------------
    # Install Docker Compose
    # -------------------------------
    log_info "Starting Docker Compose installation..."
    if ! command -v docker-compose &>/dev/null; then
        local version="2.20.2"
        curl -L "https://github.com/docker/compose/releases/download/v${version}/docker-compose-$(uname -s)-$(uname -m)" \
            -o /usr/local/bin/docker-compose || handle_error "Failed to download Docker Compose."
        chmod +x /usr/local/bin/docker-compose || handle_error "Failed to set executable permission on Docker Compose."
        log_info "Docker Compose installed successfully."
    else
        log_info "Docker Compose is already installed."
    fi
}

# copy_shell_configs
# Copies .bashrc and .profile into place from Git repo
copy_shell_configs() {
    print_section "Shell Configuration Files Update"

    local source_dir="/home/$USERNAME/github/linux/dotfiles"
    local dest_dir="/home/$USERNAME"
    local files=(".bashrc" ".profile")

    for file in "${files[@]}"; do
        local src="${source_dir}/${file}"
        local dest="${dest_dir}/${file}"
        if [ -f "$src" ]; then
            log_info "Copying ${src} to ${dest}..."
            cp -f "$src" "$dest" || log_warn "Failed to copy ${src} to ${dest}."
            chown "$USERNAME":"$USERNAME" "$dest" || log_warn "Failed to set ownership for ${dest}."
        else
            log_warn "Source file ${src} not found; skipping."
        fi
    done

    log_info "Shell configuration files update completed."
}

# configure_periodic
# Sets up a daily cron job for system maintenance (update, upgrade, autoremove).
configure_periodic() {
    print_section "Periodic Maintenance Setup"
    log_info "Configuring periodic system maintenance tasks..."
    local CRON_FILE="/etc/cron.daily/debian_maintenance"
    cat <<'EOF' > "$CRON_FILE"
#!/bin/sh
# Debian maintenance script (added by debian_setup script)
apt-get update -qq && apt-get upgrade -y && apt-get autoremove -y
EOF
    chmod +x "$CRON_FILE" || log_warn "Failed to set execute permission on $CRON_FILE"
    log_info "Periodic maintenance script created at $CRON_FILE."
}

# final_checks
# Logs some final system information for confirmation.
final_checks() {
    print_section "Final System Checks"
    log_info "Kernel version: $(uname -r)"
    log_info "Disk usage: $(df -h / | awk 'NR==2 {print $0}')"
    log_info "Physical memory: $(free -h | awk '/^Mem:/{print $2}')"
}

# prompt_reboot
# Informs the user that the setup is complete and initiates a reboot after a
# brief delay.
prompt_reboot() {
    print_section "Reboot Prompt"
    log_info "Setup complete. The system will reboot in 10 seconds. Press Ctrl+C to cancel."
    sleep 10
    shutdown -r now
}

# ------------------------------------------------------------------------------
# MAIN EXECUTION
# ------------------------------------------------------------------------------
main() {
    # Ensure the script is being executed with Bash.
    if [[ -z "${BASH_VERSION:-}" ]]; then
        echo -e "${NORD11}ERROR: Please run this script with bash.${NC}" >&2
        exit 1
    fi

    # Ensure that the log directory exists and has the proper permissions.
    local LOG_DIR
    LOG_DIR="$(dirname "$LOG_FILE")"
    if [[ ! -d "$LOG_DIR" ]]; then
        mkdir -p "$LOG_DIR" || handle_error "Failed to create log directory: $LOG_DIR"
    fi
    touch "$LOG_FILE" || handle_error "Failed to create log file: $LOG_FILE"
    chmod 600 "$LOG_FILE" || handle_error "Failed to set permissions on $LOG_FILE"

    log_info "Debian setup script execution started."

    check_root
    check_network
    update_system
    ensure_user
    configure_sudoers
    install_packages
    configure_ssh
    configure_firewall
    configure_fail2ban
    install_plex
    configure_zfs
    setup_repos
    caddy_config
    copy_shell_configs
    enable_dunamismax_services
    docker_config
    configure_periodic
    final_checks
    prompt_reboot
}

main "$@"