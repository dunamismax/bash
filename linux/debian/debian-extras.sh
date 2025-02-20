#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Debian Full – Unique Functions Only
#
# This script is structured similarly to the other Debian setup scripts,
# but it includes only those functions that are unique to the Debian full
# configuration. Do not include any functions that appear in both scripts.
#
# Unique functions included:
#   • dotfiles_load
#   • install_plex
#   • caddy_config
#   • install_configure_zfs
#   • install_zig_binary
#   • enable_dunamismax_services
#   • install_ly
#
# Note: This script assumes that common functions (e.g. log_info,
# handle_error, etc.) and configuration variables (e.g. USERNAME) are defined
# elsewhere.
#
# Author: dunamismax | License: MIT
# -----------------------------------------------------------------------------

set -Eeuo pipefail
IFS=$'\n\t'

#----------------------------------------------------------------
# dotfiles_load
# Copies additional dotfiles and configuration directories.
#----------------------------------------------------------------
dotfiles_load() {
    log_info "Copying dotfiles configuration..."
    local source_dir="/home/${USERNAME}/bash/linux/debian/dotfiles"  # Updated path

    if [ ! -d "$source_dir" ]; then
        log_warn "Dotfiles source directory $source_dir does not exist. Skipping dotfiles copy."
        return 0
    fi

    # Copy the Alacritty configuration folder.
    log_info "Copying Alacritty configuration to ~/.config/alacritty..."
    mkdir -p "/home/${USERNAME}/.config/alacritty"
    if ! rsync -a --delete "${source_dir}/alacritty/" "/home/${USERNAME}/.config/alacritty/"; then
        handle_error "Failed to copy Alacritty configuration."
    fi

    # Copy the i3 configuration folder.
    log_info "Copying i3 configuration to ~/.config/i3..."
    mkdir -p "/home/${USERNAME}/.config/i3"
    if ! rsync -a --delete "${source_dir}/i3/" "/home/${USERNAME}/.config/i3/"; then
        handle_error "Failed to copy i3 configuration."
    fi

    # Copy the i3blocks configuration folder.
    log_info "Copying i3blocks configuration to ~/.config/i3blocks..."
    mkdir -p "/home/${USERNAME}/.config/i3blocks"
    if ! rsync -a --delete "${source_dir}/i3blocks/" "/home/${USERNAME}/.config/i3blocks/"; then
        handle_error "Failed to copy i3blocks configuration."
    fi

    # Set execute permissions on all scripts within the i3blocks/scripts directory.
    log_info "Setting execute permissions for i3blocks scripts..."
    if ! chmod -R +x "/home/${USERNAME}/.config/i3blocks/scripts"; then
        log_warn "Failed to set execute permissions on i3blocks scripts."
    fi

    # Copy the picom configuration folder.
    log_info "Copying picom configuration to ~/.config/picom..."
    mkdir -p "/home/${USERNAME}/.config/picom"
    if ! rsync -a --delete "${source_dir}/picom/" "/home/${USERNAME}/.config/picom/"; then
        handle_error "Failed to copy picom configuration."
    fi

    log_info "Dotfiles loaded successfully."
}

#----------------------------------------------------------------
# install_plex
# Downloads and installs Plex Media Server from a .deb package.
#----------------------------------------------------------------
install_plex() {
  log_info "Installing Plex Media Server from downloaded .deb file..."
  if ! command -v curl >/dev/null; then
    handle_error "curl is required but not installed. Please install curl."
  fi
  local plex_url="https://downloads.plex.tv/plex-media-server-new/1.41.3.9314-a0bfb8370/debian/plexmediaserver_1.41.3.9314-a0bfb8370_amd64.deb"
  local temp_deb="/tmp/plexmediaserver.deb"
  log_info "Downloading Plex Media Server package from ${plex_url}..."
  if ! curl -L -o "$temp_deb" "$plex_url"; then
    handle_error "Failed to download Plex Media Server .deb file."
  fi
  log_info "Installing Plex Media Server package..."
  if ! dpkg -i "$temp_deb"; then
    log_warn "dpkg encountered issues. Attempting to fix missing dependencies..."
    apt install -f -y || handle_error "Failed to install dependencies for Plex Media Server."
  fi
  local PLEX_CONF="/etc/default/plexmediaserver"
  if [ -f "$PLEX_CONF" ]; then
    log_info "Configuring Plex to run as ${USERNAME}..."
    sed -i "s/^PLEX_MEDIA_SERVER_USER=.*/PLEX_MEDIA_SERVER_USER=${USERNAME}/" "$PLEX_CONF" || log_warn "Failed to set Plex user in $PLEX_CONF"
  else
    log_warn "$PLEX_CONF not found; skipping user configuration."
  fi
  log_info "Enabling Plex Media Server service..."
  systemctl enable plexmediaserver || log_warn "Failed to enable Plex Media Server service."
  rm -f "$temp_deb"
  log_info "Plex Media Server installed successfully."
}

#----------------------------------------------------------------
# caddy_config
# Releases occupied network ports and installs/configures Caddy.
#----------------------------------------------------------------
caddy_config() {
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
  apt install -y debian-keyring debian-archive-keyring apt-transport-https curl || handle_error "Failed to install dependencies for Caddy."
  log_info "Adding Caddy GPG key..."
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg || handle_error "Failed to add Caddy GPG key."
  log_info "Adding Caddy repository..."
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list || handle_error "Failed to add Caddy repository."
  log_info "Updating package lists..."
  apt update || handle_error "Failed to update package lists."
  log_info "Installing Caddy..."
  apt install -y caddy || handle_error "Failed to install Caddy."
  log_info "Caddy installed successfully."
  local CUSTOM_CADDYFILE="/home/${USERNAME}/github/linux/dotfiles/Caddyfile"
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

#----------------------------------------------------------------
# install_configure_zfs
# Installs prerequisites, ZFS packages, and configures a ZFS pool.
#----------------------------------------------------------------
install_configure_zfs() {
  local ZPOOL_NAME="WD_BLACK"
  local MOUNT_POINT="/media/${ZPOOL_NAME}"
  log_info "Updating package lists..."
  if ! apt update; then
    log_error "Failed to update package lists."
    return 1
  fi
  log_info "Installing prerequisites for ZFS..."
  if ! apt install -y dpkg-dev linux-headers-generic linux-image-generic; then
    log_error "Failed to install prerequisites."
    return 1
  fi
  log_info "Installing ZFS packages..."
  if ! DEBIAN_FRONTEND=noninteractive apt install -y zfs-dkms zfsutils-linux; then
    log_error "Failed to install ZFS packages."
    return 1
  fi
  log_info "ZFS packages installed successfully."
  log_info "Enabling ZFS auto-import and mount services..."
  systemctl enable zfs-import-cache.service || log_warn "Could not enable zfs-import-cache.service."
  systemctl enable zfs-mount.service || log_warn "Could not enable zfs-mount.service."
  if ! zpool list "$ZPOOL_NAME" >/dev/null 2>&1; then
    log_info "Importing ZFS pool '$ZPOOL_NAME'..."
    if ! zpool import -f "$ZPOOL_NAME"; then
      log_error "Failed to import ZFS pool '$ZPOOL_NAME'."
      return 1
    fi
  else
    log_info "ZFS pool '$ZPOOL_NAME' is already imported."
  fi
  log_info "Setting mountpoint for ZFS pool '$ZPOOL_NAME' to '$MOUNT_POINT'..."
  if ! zfs set mountpoint="${MOUNT_POINT}" "$ZPOOL_NAME"; then
    log_warn "Failed to set mountpoint for ZFS pool '$ZPOOL_NAME'."
  else
    log_info "Mountpoint for pool '$ZPOOL_NAME' successfully set to '$MOUNT_POINT'."
  fi
  log_info "ZFS installation and configuration finished successfully."
}

#----------------------------------------------------------------
# install_zig_binary
# Downloads and installs the official Zig binary.
#----------------------------------------------------------------
install_zig_binary() {
  log_info "Installing Zig binary from the official release..."
  local ZIG_VERSION="0.12.1"
  local ZIG_TARBALL_URL="https://ziglang.org/download/${ZIG_VERSION}/zig-linux-x86_64-${ZIG_VERSION}.tar.xz"
  local ZIG_INSTALL_DIR="/opt/zig"
  local TEMP_DOWNLOAD="/tmp/zig.tar.xz"
  log_info "Ensuring required dependencies (curl, tar) are installed..."
  apt install -y curl tar || handle_error "Failed to install required dependencies."
  log_info "Downloading Zig ${ZIG_VERSION} binary from ${ZIG_TARBALL_URL}..."
  curl -L -o "${TEMP_DOWNLOAD}" "${ZIG_TARBALL_URL}" || handle_error "Failed to download Zig binary."
  log_info "Extracting Zig to ${ZIG_INSTALL_DIR}..."
  rm -rf "${ZIG_INSTALL_DIR}"
  mkdir -p "${ZIG_INSTALL_DIR}" || handle_error "Failed to create ${ZIG_INSTALL_DIR}."
  tar -xf "${TEMP_DOWNLOAD}" -C "${ZIG_INSTALL_DIR}" --strip-components=1 || handle_error "Failed to extract Zig binary."
  log_info "Creating symlink for Zig in /usr/local/bin..."
  ln -sf "${ZIG_INSTALL_DIR}/zig" /usr/local/bin/zig || handle_error "Failed to create symlink for Zig."
  log_info "Cleaning up temporary files..."
  rm -f "${TEMP_DOWNLOAD}"
  if command -v zig &>/dev/null; then
    log_info "Zig installation completed successfully! Version: $(zig version)"
  else
    handle_error "Zig is not accessible from the command line."
  fi
}

#----------------------------------------------------------------
# enable_dunamismax_services
# Creates and enables custom DunamisMax systemd services.
#----------------------------------------------------------------
enable_dunamismax_services() {
  log_info "Enabling DunamisMax website services..."
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
  systemctl daemon-reload
  systemctl enable dunamismax-ai-agents.service
  systemctl enable dunamismax-files.service
  systemctl enable dunamismax-messenger.service
  systemctl enable dunamismax-notes.service
  systemctl enable dunamismax.service
  log_info "DunamisMax services enabled."
}

#----------------------------------------------------------------
# install_ly
# Clones, builds, and installs the Ly display manager.
#----------------------------------------------------------------
install_ly() {
  log_info "Installing Ly Display Manager..."
  local required_cmds=(git zig systemctl)
  for cmd in "${required_cmds[@]}"; do
    if ! command -v "$cmd" &>/dev/null; then
      handle_error "'$cmd' is not installed. Please install it and try again."
    fi
  done
  log_info "Installing Ly build dependencies..."
  apt update || handle_error "Failed to update package lists before installing dependencies."
  if ! apt install -y build-essential libpam0g-dev libxcb-xkb-dev libxcb-randr0-dev libxcb-xinerama0-dev libxcb-xrm-dev libxkbcommon-dev libxkbcommon-x11-dev; then
    handle_error "Failed to install Ly build dependencies."
  fi
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
  cd "$LY_DIR" || handle_error "Failed to change directory to $LY_DIR."
  log_info "Compiling Ly with Zig..."
  if ! zig build; then
    handle_error "Compilation of Ly failed."
  fi
  log_info "Installing Ly systemd service..."
  if ! zig build installsystemd; then
    handle_error "Installation of Ly systemd service failed."
  fi
  log_info "Disabling conflicting display managers..."
  local dm_list=(gdm sddm lightdm lxdm)
  for dm in "${dm_list[@]}"; do
    if systemctl is-enabled "${dm}.service" &>/dev/null; then
      log_info "Disabling ${dm}.service..."
      if ! systemctl disable --now "${dm}.service"; then
        handle_error "Failed to disable ${dm}.service."
      fi
    fi
  done
  if [ -L /etc/systemd/system/display-manager.service ]; then
    log_info "Removing leftover /etc/systemd/system/display-manager.service symlink..."
    if ! rm /etc/systemd/system/display-manager.service; then
      log_warn "Failed to remove display-manager.service symlink."
    fi
  fi
  log_info "Enabling ly.service for next boot..."
  if ! systemctl enable ly.service; then
    handle_error "Failed to enable ly.service."
  fi
  log_info "Disabling getty@tty2.service..."
  if ! systemctl disable getty@tty2.service; then
    handle_error "Failed to disable getty@tty2.service."
  fi
  log_info "Ly has been installed and configured as the default login manager."
  log_info "Ly will take effect on next reboot, or start it now with: systemctl start ly.service"
}