#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

# Log file location
LOG_FILE="/var/log/freebsd_voip_setup.log"
mkdir -p "$(dirname "$LOG_FILE")"
touch "$LOG_FILE"
chmod 600 "$LOG_FILE"

log() {
  local level="${1:-INFO}"
  shift
  local message="$*"
  local timestamp
  timestamp="$(date +"%Y-%m-%d %H:%M:%S")"
  local entry="[$timestamp] [${level^^}] $message"
  echo "$entry" >> "$LOG_FILE"
  echo "$entry"
}
log_info() { log INFO "$@"; }
log_warn() { log WARN "$@"; }

# Check for root privileges
check_root() {
  if [ "$(id -u)" -ne 0 ]; then
    log_warn "Script must be run as root. Exiting."
    exit 1
  fi
}

# Check network connectivity (non-interactive check)
check_network() {
  log_info "Checking network connectivity..."
  if ! ping -c1 -t5 google.com &>/dev/null; then
    log_warn "No network connectivity detected. Exiting."
    exit 1
  else
    log_info "Network connectivity OK."
  fi
}

# Update pkg repository and upgrade installed packages
update_system() {
  log_info "Updating pkg repository..."
  pkg update || log_warn "pkg update encountered issues."
  log_info "Upgrading installed packages..."
  pkg upgrade -y || log_warn "pkg upgrade encountered issues."
}

# Install required packages (non-interactively)
install_packages() {
  PACKAGES=(
    # System utilities
    bash vim nano git curl wget sudo screen tmux htop

    # Asterisk and its configuration package
    asterisk asterisk-config

    # (Optional) MariaDB for CDR/config back-end
    mariadb105-server mariadb105-client

    # (Optional) pfSense-style firewall management is done manually later.
    # You might add additional packages as needed.
  )
  log_info "Installing required packages for the VoIP system..."
  pkg install -y "${PACKAGES[@]}" || log_warn "One or more packages failed to install."

  # Enable necessary services
  sysrc asterisk_enable="YES"
  sysrc mariadb_enable="YES"
  service asterisk start || log_warn "Failed to start Asterisk service."
  service mariadb start || log_warn "Failed to start MariaDB service."
}

# Create (or verify) the Asterisk user
create_asterisk_user() {
  if ! id asterisk &>/dev/null; then
    log_info "Creating 'asterisk' user..."
    pw useradd asterisk -m -s /usr/local/bin/bash || log_warn "Failed to create 'asterisk' user."
  else
    log_info "'asterisk' user already exists."
  fi
}

# Configure Asterisk to use G.722 as its primary codec and set up a basic dialplan.
configure_asterisk() {
  log_info "Configuring Asterisk for G.722 wideband audio..."

  AST_CONFIG_DIR="/usr/local/etc/asterisk"
  mkdir -p "${AST_CONFIG_DIR}"

  # Create custom SIP configuration to allow only G.722 (and optionally ulaw)
  SIP_CONF="${AST_CONFIG_DIR}/sip_custom.conf"
  cat << 'EOF' > "$SIP_CONF"
[general]
; Disable all codecs first
disallow=all
; Allow high-quality wideband G.722 codec
allow=g722
; (Optional fallback: allow ulaw for legacy endpoints)
; allow=ulaw
EOF
  log_info "Created SIP configuration at $SIP_CONF."

  # Create a basic dialplan in extensions_custom.conf
  EXT_CONF="${AST_CONFIG_DIR}/extensions_custom.conf"
  cat << 'EOF' > "$EXT_CONF"
[internal]
; Simple dialplan: dial a SIP endpoint (assumes endpoints are named by extension number)
exten => _X.,1,NoOp(Incoming call for extension ${EXTEN})
 same => n,Dial(SIP/${EXTEN},20)
 same => n,Hangup()

[default]
; Fallback context plays a greeting message
exten => s,1,Answer()
 same => n,Playback(hello-world)
 same => n,Hangup()
EOF
  log_info "Created basic dialplan at $EXT_CONF."

  # (Optional) Configure SIP endpoints here. For an automated test setup, you might add:
  cat << 'EOF' >> "$SIP_CONF"

[6001]
type=friend
context=internal
host=dynamic
secret=changeme6001
callerid=Phone 6001 <6001>
disallow=all
allow=g722

[6002]
type=friend
context=internal
host=dynamic
secret=changeme6002
callerid=Phone 6002 <6002>
disallow=all
allow=g722
EOF
  log_info "Added sample SIP endpoints to $SIP_CONF."

  # Reload Asterisk configuration (assumes Asterisk is running)
  if asterisk -rx "core reload" ; then
    log_info "Asterisk configuration reloaded successfully."
  else
    log_warn "Failed to reload Asterisk configuration."
  fi
}

# Configure pf (FreeBSD firewall) to allow SIP and RTP traffic non-interactively
configure_pf() {
  log_info "Configuring pf firewall rules for SIP and RTP..."
  PF_CONF="/etc/pf.conf"
  # Backup the original pf.conf
  cp "$PF_CONF" "${PF_CONF}.bak.$(date +%Y%m%d%H%M%S)" || log_warn "Failed to backup pf.conf."
  # Append basic rules if they are not already present.
  if ! grep -q "pass in quick on egress proto udp from any to any port 5060" "$PF_CONF"; then
    cat << 'EOF' >> "$PF_CONF"

# --- Begin SIP/RTP rules added by setup_voip.sh ---
pass in quick on egress proto udp from any to any port 5060
pass in quick on egress proto udp from any to any port 16384:32767
pass out quick on egress proto udp from any to any port 5060
pass out quick on egress proto udp from any to any port 16384:32767
# --- End SIP/RTP rules ---
EOF
    log_info "Appended SIP/RTP rules to $PF_CONF."
  else
    log_info "SIP/RTP rules already present in $PF_CONF."
  fi
  # Reload pf
  pfctl -f "$PF_CONF" && pfctl -e || log_warn "Failed to reload or enable pf."
}

# Final system checks
final_checks() {
  log_info "Final system checks:"
  echo "FreeBSD version: $(uname -r)"
  echo "Asterisk status:" && service asterisk status
  echo "MariaDB status:" && service mariadb status
  df -h /
}

# Automatically reboot the system without prompt (non-interactive)
auto_reboot() {
  log_info "Rebooting system now to apply all changes..."
  reboot
}

# Main function that runs all setup steps non-interactively
main() {
  check_root
  check_network
  update_system
  install_packages
  create_asterisk_user
  configure_asterisk
  configure_pf
  final_checks
  auto_reboot
}

main "$@"