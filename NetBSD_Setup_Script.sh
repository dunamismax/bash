#!/bin/ash
# ------------------------------------------------------------------------------
# Enhanced NetBSD Automated Setup Script (Simplified for Ash)
# ------------------------------------------------------------------------------
# Comprehensive system configuration and hardening script for NetBSD
#
# Features:
#  • System hardening and security configurations
#  • Package management and system updates
#  • Service configuration (SSH, NTP, fail2ban)
#  • Development environment setup
#  • Backup functionality
#  • User environment configuration
#
# Usage: sudo ./netbsd_setup.sh [--verbose] [--no-backup] [--minimal]
# ------------------------------------------------------------------------------

set -e

# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
SCRIPT_VERSION="2.0.0"
LOG_FILE="/var/log/netbsd_setup.log"
BACKUP_DIR="/var/backups/system"
VERBOSE=2
USERNAME="${USERNAME:-sawyer}"
ENABLE_HARDENING="${ENABLE_HARDENING:-true}"

TIMEZONE="America/New_York"
SSH_PORT="22"
MAX_AUTH_TRIES="6"
BACKUP_RETENTION_DAYS="7"

# ------------------------------------------------------------------------------
# Function: log
# ------------------------------------------------------------------------------
log() {
  level="$1"; shift
  message="$*"
  echo "$(date '+%Y-%m-%d %H:%M:%S') [$level] $message" | tee -a "$LOG_FILE"
}

# ------------------------------------------------------------------------------
# Function: die
# ------------------------------------------------------------------------------
die() {
  log ERROR "$1"
  exit "${2:-1}"
}

# ------------------------------------------------------------------------------
# Function: cleanup
# ------------------------------------------------------------------------------
cleanup() {
  rm -f /tmp/netbsd_setup.* 2>/dev/null || true
  [ -f /tmp/netbsd_setup.lock ] && rm -f /tmp/netbsd_setup.lock
  log INFO "Cleanup completed"
}

# ------------------------------------------------------------------------------
# Function: check_requirements
# ------------------------------------------------------------------------------
check_requirements() {
  log INFO "Checking system requirements..."

  version=$(uname -r)
  case "$version" in
    [0-9]*.[0-9]*)
      ;; 
    *) 
      die "Unsupported NetBSD version: $version" 
      ;;
  esac

  available_space=$(df -k / | awk 'NR==2 {print $4}')
  if [ "$available_space" -lt 5242880 ]; then
    die "Insufficient disk space. At least 5GB required."
  fi

  total_mem=$(sysctl -n hw.physmem)
  if [ "$total_mem" -lt 1073741824 ]; then
    die "Insufficient memory. At least 1GB required."
  fi

  for cmd in pkgin wget curl awk sed; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      die "Required command not found: $cmd"
    fi
  done

  log INFO "System requirements check passed."
}

# ------------------------------------------------------------------------------
# Function: parse_arguments
# ------------------------------------------------------------------------------
parse_arguments() {
  while [ $# -gt 0 ]; do
    case "$1" in
      --verbose)
        VERBOSE=2
        ;;
      --quiet)
        VERBOSE=0
        ;;
      --no-backup)
        SKIP_BACKUP=true
        ;;
      --minimal)
        MINIMAL_INSTALL=true
        ;;
      --help)
        echo "Usage: $0 [--verbose] [--no-backup] [--minimal]"
        exit 0
        ;;
      *)
        die "Unknown option: $1"
        ;;
    esac
    shift
  done
}

# ------------------------------------------------------------------------------
# Function: enhanced_backup_system
# ------------------------------------------------------------------------------
enhanced_backup_system() {
  if [ "$SKIP_BACKUP" = true ]; then
    log INFO "Backup skipped due to --no-backup flag"
    return
  fi

  log INFO "Starting enhanced system backup..."

  mkdir -p -m 0700 "$BACKUP_DIR" || true

  backup_date=$(date +%Y%m%d_%H%M%S)
  backup_path="${BACKUP_DIR}/backup_${backup_date}"
  manifest_file="${backup_path}_manifest.txt"

  {
    echo "Backup Date: $(date)"
    echo "System Version: $(uname -a)"
    echo "Installed Packages:"
    pkgin list || echo "Failed to list packages"
    echo "Disk Usage:"
    df -h || echo "Failed to get disk usage"
  } > "$manifest_file"

  config_files="/etc/rc.conf /etc/ssh/sshd_config /etc/passwd /etc/group /etc/fstab"
  for file in $config_files; do
    [ -f "$file" ] && install -D -m 0600 "$file" "${backup_path}${file}"
  done

  tar czf "${backup_path}.tar.gz" \
    --exclude="/proc/*" \
    --exclude="/sys/*" \
    --exclude="/tmp/*" \
    --exclude="/var/tmp/*" \
    --exclude="/var/cache/*" \
    --exclude="$BACKUP_DIR" \
    /etc /usr/local/etc /home/"$USERNAME"/.config

  if ! tar tzf "${backup_path}.tar.gz" >/dev/null 2>&1; then
    die "Backup verification failed"
  fi

  find "$BACKUP_DIR" -type f -name "backup_*" -mtime +"$BACKUP_RETENTION_DAYS" -delete

  log INFO "Backup completed successfully: ${backup_path}.tar.gz"
}

# ------------------------------------------------------------------------------
# Function: harden_system
# ------------------------------------------------------------------------------
harden_system() {
  if [ "$ENABLE_HARDENING" != true ]; then
    log INFO "System hardening skipped due to configuration"
    return
  fi

  log INFO "Applying system hardening measures..."

  sysctl_conf="/etc/sysctl.conf"
  # Apply a few static sysctl settings
  for param in "security.bsd.see_other_uids=0" \
               "security.bsd.see_other_gids=0" \
               "security.bsd.unprivileged_proc_debug=0" \
               "security.bsd.hardlink_check_uid=1" \
               "security.bsd.hardlink_check_gid=1"; do
    key=${param%%=*}
    value=${param#*=}
    if grep -q "^$key=" "$sysctl_conf" 2>/dev/null; then
      sed -i "s/^$key=.*/$key=$value/" "$sysctl_conf"
    else
      echo "$key=$value" >> "$sysctl_conf"
    fi
  done

  sysctl -p || log WARN "Failed to apply some sysctl parameters"

  chmod 700 /root
  chmod 700 /home/"$USERNAME"
  chmod 600 /etc/ssh/ssh_host_*_key 2>/dev/null || true
  chmod 644 /etc/ssh/ssh_host_*_key.pub 2>/dev/null || true

  if [ -f /etc/pam.d/system ]; then
    sed -i '/^auth/i auth required pam_listfile.so item=user sense=deny file=/etc/ssh/deniedusers onerr=succeed' /etc/pam.d/system
  fi

  if [ -f /etc/login.conf ]; then
    cat >> /etc/login.conf <<'EOF'
default:\
        :passwordtime=90:\
        :mixpasswordcase=true:\
        :minpasswordlen=12:\
        :minpasswordrepeat=3:\
        :login-retries=5:\
        :login-backoff=10:\
        :idletime=30:\
        :passwordcheck=yes:
EOF
    cap_mkdb /etc/login.conf
  fi

  log INFO "System hardening completed"
}

# ------------------------------------------------------------------------------
# Function: enhanced_configure_ssh
# ------------------------------------------------------------------------------
enhanced_configure_ssh() {
  log INFO "Configuring enhanced SSH security..."

  sshd_config="/etc/ssh/sshd_config"
  sshd_config_backup="${sshd_config}.bak.$(date +%Y%m%d%H%M%S)"

  cp "$sshd_config" "$sshd_config_backup"

  cat > "$sshd_config" <<EOF
# Security-hardened SSH Configuration
Port $SSH_PORT
Protocol 2
HostKey /etc/ssh/ssh_host_ed25519_key
HostKey /etc/ssh/ssh_host_rsa_key

LoginGraceTime 30
PermitRootLogin no
StrictModes yes
MaxAuthTries $MAX_AUTH_TRIES
MaxSessions 4
PubkeyAuthentication yes
PasswordAuthentication no
PermitEmptyPasswords no
ChallengeResponseAuthentication no
KerberosAuthentication no
GSSAPIAuthentication no

X11Forwarding no
AllowTcpForwarding no
AllowAgentForwarding no
PermitTunnel no
PermitUserEnvironment no
ClientAliveInterval 300
ClientAliveCountMax 2
UsePAM yes

SyslogFacility AUTH
LogLevel VERBOSE

AllowUsers $USERNAME
EOF

  chmod 600 "$sshd_config"

  if [ ! -f /etc/ssh/ssh_host_ed25519_key ]; then
    ssh-keygen -t ed25519 -f /etc/ssh/ssh_host_ed25519_key -N ""
  fi

  if ! grep -q "^sshd=YES" /etc/rc.conf 2>/dev/null; then
    echo "sshd=YES" >> /etc/rc.conf
  fi

  service sshd restart || log ERROR "Failed to restart SSH service"

  log INFO "SSH configuration completed"
}

# ------------------------------------------------------------------------------
# Function: configure_development_environment
# ------------------------------------------------------------------------------
configure_development_environment() {
  log INFO "Setting up development environment..."

  for pkg in git gcc g++ make cmake python3 python3-pip rust cargo nodejs npm go; do
    pkgin install -y "$pkg" || log WARN "Failed to install $pkg"
  done

  if command -v git >/dev/null 2>&1; then
    su - "$USERNAME" -c "git config --global core.fileMode true"
    su - "$USERNAME" -c "git config --global core.autocrlf input"
    su - "$USERNAME" -c "git config --global init.defaultBranch main"
  fi

  if command -v python3 >/dev/null 2>&1; then
    su - "$USERNAME" -c "python3 -m venv /home/$USERNAME/.venv"
  fi

  if ! command -v rustc >/dev/null 2>&1; then
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
  fi

  if command -v go >/dev/null 2>&1; then
    su - "$USERNAME" -c "go install golang.org/x/tools/gopls@latest"
    su - "$USERNAME" -c "go install golang.org/x/tools/cmd/goimports@latest"
  fi

  log INFO "Development environment setup completed"
}

# ------------------------------------------------------------------------------
# Function: setup_monitoring
# ------------------------------------------------------------------------------
setup_monitoring() {
  log INFO "Setting up system monitoring..."

  for pkg in top htop systat mrtg munin-node; do
    pkgin install -y "$pkg" || log WARN "Failed to install $pkg"
  done

  if command -v munin-node >/dev/null 2>&1; then
    if ! grep -q "^munin_node=YES" /etc/rc.conf 2>/dev/null; then
      echo "munin_node=YES" >> /etc/rc.conf
    fi

    cat > /etc/munin/munin-node.conf <<'EOF'
log_level 4
log_file /var/log/munin/munin-node.log
pid_file /var/run/munin/munin-node.pid

host *
port 4949
user root
group root

cidr_allow 127.0.0.0/8
EOF

    service munin-node restart || log WARN "Failed to restart Munin node"
  fi

  mkdir -p /usr/local/bin/monitoring

  cat > /usr/local/bin/monitoring/check_disk_space.sh <<'EOF'
#!/bin/sh
THRESHOLD=90
df -h | awk 'NR>1 && $5 ~ /%/ {gsub(/%/,"",$5); if ($5 > ENVIRON["THRESHOLD"]) printf "ALERT: Partition %s is %s%% full\n", $6, $5}'
EOF

  cat > /usr/local/bin/monitoring/check_memory.sh <<'EOF'
#!/bin/sh
vmstat 1 2 | awk 'NR==4 {
    free=$5;
    "sysctl -n hw.physmem" | getline total;
    total = total / 1024;
    used = total - free;
    pct = used / total * 100;
    if (pct > 90) {
        printf "ALERT: Memory usage at %.2f%%\n", pct
    }
}'
EOF

  chmod +x /usr/local/bin/monitoring/*.sh
  chown -R root:wheel /usr/local/bin/monitoring

  crontab -l > /tmp/crontab.tmp 2>/dev/null || true
  {
    echo "*/5 * * * * /usr/local/bin/monitoring/check_disk_space.sh"
    echo "*/5 * * * * /usr/local/bin/monitoring/check_memory.sh"
  } >> /tmp/crontab.tmp
  crontab /tmp/crontab.tmp
  rm -f /tmp/crontab.tmp

  log INFO "System monitoring setup completed"
}

# ------------------------------------------------------------------------------
# Function: setup_user_environment
# ------------------------------------------------------------------------------
setup_user_environment() {
  log INFO "Setting up user environment for $USERNAME..."

  if ! id -u "$USERNAME" >/dev/null 2>&1; then
    useradd -m -s /bin/sh -G wheel "$USERNAME" || true
    log INFO "User $USERNAME created"
  fi

  shell_config_dir="/home/$USERNAME/.config/shell"
  mkdir -p "$shell_config_dir"

  cat > "/home/$USERNAME/.bashrc" <<'EOF'
# Enhanced .bashrc configuration
export EDITOR=vim
export VISUAL=vim
export PAGER=less
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export TERM=xterm-256color

HISTSIZE=10000
HISTFILESIZE=20000
HISTCONTROL=ignoreboth
HISTIGNORE="ls:cd:pwd:exit:date:* --help"

alias ll='ls -lah'
alias la='ls -A'
alias l='ls -CF'
alias ..='cd ..'
alias ...='cd ../..'
EOF

  mkdir -p "/home/$USERNAME/.vim" && \
  cat > "/home/$USERNAME/.vimrc" <<'EOF'
" Enhanced Vim Configuration
set nocompatible
syntax on
set number
set relativenumber
EOF

  cat > "/home/$USERNAME/.tmux.conf" <<'EOF'
# Enhanced tmux Configuration
set -g default-terminal "screen-256color"
set -g mouse on
EOF

  chown -R "$USERNAME:$USERNAME" "/home/$USERNAME"
  chmod 700 "/home/$USERNAME/.ssh" 2>/dev/null || true

  log INFO "User environment setup completed"
}

# ------------------------------------------------------------------------------
# Function: main
# ------------------------------------------------------------------------------
main() {
  trap cleanup EXIT INT TERM
  check_requirements
  parse_arguments "$@"

  log INFO "Starting NetBSD system configuration (v$SCRIPT_VERSION)"

  enhanced_backup_system
  harden_system
  enhanced_configure_ssh
  configure_development_environment
  setup_monitoring
  setup_user_environment

  log INFO "Configuration completed successfully"
  log INFO "Script execution completed successfully"
}

main "$@"