#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Enhanced NetBSD Automated Setup Script
# ------------------------------------------------------------------------------
# Comprehensive system configuration and hardening script for NetBSD
#
# Features:
#  • Robust error handling and logging
#  • System hardening and security configurations
#  • Package management and system updates
#  • Service configuration (SSH, NTP, fail2ban)
#  • Development environment setup
#  • Backup functionality
#  • User environment configuration
#
# Usage: sudo ./netbsd_setup.sh [--verbose] [--no-backup] [--minimal]
#
# Author: dunamismax | Enhanced for NetBSD | License: MIT
# ------------------------------------------------------------------------------

set -Eeuo pipefail
shopt -s nullglob

# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
readonly SCRIPT_VERSION="2.0.0"
readonly LOG_FILE="/var/log/netbsd_setup.log"
readonly BACKUP_DIR="/var/backups/system"
readonly CONFIG_DIR="/etc/netbsd-setup"
readonly VERBOSE="${VERBOSE:-2}"
readonly USERNAME="${USERNAME:-sawyer}"
readonly ENABLE_HARDENING="${ENABLE_HARDENING:-true}"

# System configuration
readonly TIMEZONE="America/New_York"
readonly SSH_PORT="22"
readonly MAX_AUTH_TRIES="6"
readonly BACKUP_RETENTION_DAYS="7"

# Package groups
declare -A PACKAGE_GROUPS=(
  ["base"]="bash zsh fish vim nano mc screen tmux"
  ["dev"]="git curl wget cmake ninja meson pkgconf"
  ["security"]="fail2ban nmap tcpdump"
  ["utils"]="rsync htop neofetch tig jq tree fzf lynx"
  ["python"]="python3 python3-pip python3-venv"
  ["system"]="smartmontools ntfs-3g cups neovim"
)

# ------------------------------------------------------------------------------
# Function: setup_trap_handlers
# ------------------------------------------------------------------------------
setup_trap_handlers() {
  trap 'handle_error $? $LINENO $BASH_LINENO "$BASH_COMMAND" $(printf "::%s" ${FUNCNAME[@]:-})' ERR
  trap 'cleanup' EXIT
  trap 'die "Script interrupted." 130' INT TERM
}

# ------------------------------------------------------------------------------
# Function: handle_error
# ------------------------------------------------------------------------------
handle_error() {
  local exit_code=$1
  local line_no=$2
  local bash_lineno=$3
  local last_cmd=$4
  local func_trace=$5

  log ERROR "Error in script execution:"
  log ERROR "Exit code: $exit_code"
  log ERROR "Command: $last_cmd"
  log ERROR "Line: $line_no"
  log ERROR "Function trace: $func_trace"

  if [[ -f "$LOG_FILE" ]]; then
    log INFO "Last 10 lines of log file:"
    tail -n 10 "$LOG_FILE" | while read -r line; do
      log INFO "  $line"
    done
  fi

  cleanup
  exit "$exit_code"
}

# ------------------------------------------------------------------------------
# Function: cleanup
# ------------------------------------------------------------------------------
cleanup() {
  local exit_code=$?
  
  # Remove temporary files
  rm -f /tmp/netbsd_setup.* 2>/dev/null || true
  
  # Reset system state if needed
  if [[ -f /tmp/netbsd_setup.lock ]]; then
    rm -f /tmp/netbsd_setup.lock
  fi

  log INFO "Cleanup completed with exit code: $exit_code"
}

# ------------------------------------------------------------------------------
# Function: die
# ------------------------------------------------------------------------------
die() {
  local msg=$1
  local code=${2:-1}
  log ERROR "$msg"
  exit "$code"
}

# ------------------------------------------------------------------------------
# Function: check_requirements
# ------------------------------------------------------------------------------
check_requirements() {
  log INFO "Checking system requirements..."

  # Check NetBSD version
  local version
  version=$(uname -r)
  if [[ ! "$version" =~ ^[0-9]+\.[0-9]+ ]]; then
    die "Unsupported NetBSD version: $version"
  }

  # Check available disk space
  local available_space
  available_space=$(df -k / | awk 'NR==2 {print $4}')
  if ((available_space < 5242880)); then  # 5GB in KB
    die "Insufficient disk space. At least 5GB required."
  }

  # Check memory
  local total_mem
  total_mem=$(sysctl -n hw.physmem)
  if ((total_mem < 1073741824)); then  # 1GB in bytes
    die "Insufficient memory. At least 1GB required."
  }

  # Check for required commands
  local required_commands=(pkgin wget curl awk sed)
  for cmd in "${required_commands[@]}"; do
    if ! command -v "$cmd" >/dev/null; then
      die "Required command not found: $cmd"
    fi
  }

  log INFO "System requirements check passed."
}

# ------------------------------------------------------------------------------
# Function: parse_arguments
# ------------------------------------------------------------------------------
parse_arguments() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --verbose)
        VERBOSE=2
        shift
        ;;
      --quiet)
        VERBOSE=0
        shift
        ;;
      --no-backup)
        SKIP_BACKUP=true
        shift
        ;;
      --minimal)
        MINIMAL_INSTALL=true
        shift
        ;;
      --help)
        show_help
        exit 0
        ;;
      *)
        die "Unknown option: $1"
        ;;
    esac
  done
}

# ------------------------------------------------------------------------------
# Function: enhanced_backup_system
# ------------------------------------------------------------------------------
enhanced_backup_system() {
  if [[ "${SKIP_BACKUP:-false}" == true ]]; then
    log INFO "Backup skipped due to --no-backup flag"
    return 0
  }

  log INFO "Starting enhanced system backup..."

  # Create backup directory with secure permissions
  install -d -m 0700 "$BACKUP_DIR"

  local backup_date
  backup_date=$(date +%Y%m%d_%H%M%S)
  local backup_path="${BACKUP_DIR}/backup_${backup_date}"
  
  # Create backup manifest
  local manifest_file="${backup_path}_manifest.txt"
  {
    echo "Backup Date: $(date)"
    echo "System Version: $(uname -a)"
    echo "Installed Packages:"
    pkgin list || echo "Failed to list packages"
    echo "Disk Usage:"
    df -h || echo "Failed to get disk usage"
  } > "$manifest_file"

  # Backup critical configuration files
  local config_files=(
    "/etc/rc.conf"
    "/etc/ssh/sshd_config"
    "/etc/passwd"
    "/etc/group"
    "/etc/fstab"
  )

  for file in "${config_files[@]}"; do
    if [[ -f "$file" ]]; then
      local backup_file="${backup_path}${file}"
      install -D -m 0600 "$file" "$backup_file"
    fi
  done

  # Create compressed archive
  tar czf "${backup_path}.tar.gz" \
    --exclude="/proc/*" \
    --exclude="/sys/*" \
    --exclude="/tmp/*" \
    --exclude="/var/tmp/*" \
    --exclude="/var/cache/*" \
    --exclude="$BACKUP_DIR" \
    /etc /usr/local/etc /home/"$USERNAME"/.config

  # Verify backup integrity
  if ! tar tzf "${backup_path}.tar.gz" >/dev/null 2>&1; then
    die "Backup verification failed"
  fi

  # Cleanup old backups
  find "$BACKUP_DIR" -type f -name "backup_*" -mtime +"$BACKUP_RETENTION_DAYS" -delete

  log INFO "Backup completed successfully: ${backup_path}.tar.gz"
}

# ------------------------------------------------------------------------------
# Function: harden_system
# ------------------------------------------------------------------------------
harden_system() {
  if [[ "${ENABLE_HARDENING:-true}" != true ]]; then
    log INFO "System hardening skipped due to configuration"
    return 0
  }

  log INFO "Applying system hardening measures..."

  # Kernel security parameters
  local sysctl_conf="/etc/sysctl.conf"
  declare -A sysctl_params=(
    ["security.bsd.see_other_uids"]=0
    ["security.bsd.see_other_gids"]=0
    ["security.bsd.unprivileged_proc_debug"]=0
    ["security.bsd.hardlink_check_uid"]=1
    ["security.bsd.hardlink_check_gid"]=1
  )

  for param in "${!sysctl_params[@]}"; do
    if ! grep -q "^${param}=" "$sysctl_conf" 2>/dev/null; then
      echo "${param}=${sysctl_params[$param]}" >> "$sysctl_conf"
    else
      sed -i "s/^${param}=.*/${param}=${sysctl_params[$param]}/" "$sysctl_conf"
    fi
  done

  # Apply sysctl changes
  sysctl -p || log WARN "Failed to apply some sysctl parameters"

  # Secure file permissions
  chmod 700 /root
  chmod 700 /home/"$USERNAME"
  chmod 600 /etc/ssh/ssh_host_*_key
  chmod 644 /etc/ssh/ssh_host_*_key.pub

  # Configure PAM
  if [[ -f /etc/pam.d/system ]]; then
    sed -i '/^auth/i auth required pam_listfile.so item=user sense=deny file=/etc/ssh/deniedusers onerr=succeed' /etc/pam.d/system
  fi

  # Setup password policies
  if [[ -f /etc/login.conf ]]; then
    cat >> /etc/login.conf << EOF
default:\\
        :passwordtime=90:\\
        :mixpasswordcase=true:\\
        :minpasswordlen=12:\\
        :minpasswordrepeat=3:\\
        :passwordtime=90:\\
        :login-retries=5:\\
        :login-backoff=10:\\
        :idletime=30:\\
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

  local sshd_config="/etc/ssh/sshd_config"
  local sshd_config_backup="${sshd_config}.bak.$(date +%Y%m%d%H%M%S)"

  # Backup existing configuration
  cp "$sshd_config" "$sshd_config_backup"

  # Generate new configuration
  cat > "$sshd_config" << EOF
# Security-hardened SSH Configuration
Port ${SSH_PORT}
Protocol 2
HostKey /etc/ssh/ssh_host_ed25519_key
HostKey /etc/ssh/ssh_host_rsa_key

# Authentication
LoginGraceTime 30
PermitRootLogin no
StrictModes yes
MaxAuthTries ${MAX_AUTH_TRIES}
MaxSessions 4
PubkeyAuthentication yes
PasswordAuthentication no
PermitEmptyPasswords no
ChallengeResponseAuthentication no
KerberosAuthentication no
GSSAPIAuthentication no

# Security
X11Forwarding no
AllowTcpForwarding no
AllowAgentForwarding no
PermitTunnel no
PermitUserEnvironment no
ClientAliveInterval 300
ClientAliveCountMax 2
UsePAM yes

# Logging
SyslogFacility AUTH
LogLevel VERBOSE

# Allowed users/groups
AllowUsers ${USERNAME}
EOF

  chmod 600 "$sshd_config"

  # Generate new host keys if needed
  if [[ ! -f /etc/ssh/ssh_host_ed25519_key ]]; then
    ssh-keygen -t ed25519 -f /etc/ssh/ssh_host_ed25519_key -N ""
  fi

  # Configure SSH service
  if ! grep -q "^sshd=YES" /etc/rc.conf; then
    echo "sshd=YES" >> /etc/rc.conf
  fi

  # Restart SSH service
  service sshd restart || log ERROR "Failed to restart SSH service"

  log INFO "SSH configuration completed"
}

# ------------------------------------------------------------------------------
# Function: configure_development_environment
# ------------------------------------------------------------------------------
configure_development_environment() {
  log INFO "Setting up development environment..."

  # Install development tools
  local dev_packages=(
    git gcc g++ make cmake
    python3 python3-pip
    rust cargo
    nodejs npm
    go
  )

  for pkg in "${dev_packages[@]}"; do
    pkgin install -y "$pkg" || log WARN "Failed to install $pkg"
  done

  # Configure Git
  git config --global core.fileMode true
  git config --global core.autocrlf input
  git config --global init.defaultBranch main

  # Setup Python virtual environment
  if command -v python3 >/dev/null; then
    python3 -m venv "/home/$USERNAME/.venv"
    chown -R "$USERNAME:$USERNAME" "/home/$USERNAME/.venv"
  fi

  # Install Rust via rustup if not present
  if ! command -v rustc >/dev/null; then
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
  fi

  # Install Go tools
  if command -v go >/dev/null; then
    go install golang.org/x/tools/gopls@latest
    go install golang.org/x/tools/cmd/goimports@latest
  fi

  log INFO "Development environment setup completed"
}

# ------------------------------------------------------------------------------
# Function: setup_monitoring
# ------------------------------------------------------------------------------
setup_monitoring() {
  log INFO "Setting up system monitoring..."

  # Install monitoring tools
  local monitoring_packages=(
    top htop
    systat
    mrtg
    munin-node
  )

  for pkg in "${monitoring_packages[@]}"; do
    pkgin install -y "$pkg" || log WARN "Failed to install $pkg"
  done

  # Configure Munin node if installed
  if command -v munin-node >/dev/null; then
    if ! grep -q "^munin_node=YES" /etc/rc.conf; then
      echo "munin_node=YES" >> /etc/rc.conf
    fi

    # Basic Munin configuration
    cat > /etc/munin/munin-node.conf << EOF
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

  # Setup basic system monitoring scripts
  mkdir -p "/usr/local/bin/monitoring"
  
  # Create disk space monitoring script
  cat > "/usr/local/bin/monitoring/check_disk_space.sh" << 'EOF'
#!/bin/sh
THRESHOLD=90
df -h | awk 'NR>1 && $5 ~ /%/ {gsub(/%/,"",$5); if ($5 > THRESHOLD) printf "ALERT: Partition %s is %s%% full\n", $</antArtifact>
THRESHOLD=90
df -h | awk 'NR>1 && $5 ~ /%/ {gsub(/%/,"",$5); if ($5 > THRESHOLD) printf "ALERT: Partition %s is %s%% full\n", $6, $5}'
EOF

  # Create memory monitoring script
  cat > "/usr/local/bin/monitoring/check_memory.sh" << 'EOF'
#!/bin/sh
vmstat 1 2 | awk 'NR==4 {
    free=$5
    total=`sysctl -n hw.physmem`/1024
    used=total-free
    pct=used/total*100
    if (pct > 90) {
        printf "ALERT: Memory usage at %.2f%%\n", pct
    }
}'
EOF

  # Set permissions and ownership
  chmod +x /usr/local/bin/monitoring/*.sh
  chown -R root:wheel /usr/local/bin/monitoring

  # Setup cron jobs for monitoring
  crontab -l > /tmp/crontab.tmp || true
  {
    echo "*/5 * * * * /usr/local/bin/monitoring/check_disk_space.sh"
    echo "*/5 * * * * /usr/local/bin/monitoring/check_memory.sh"
  } >> /tmp/crontab.tmp
  crontab /tmp/crontab.tmp
  rm /tmp/crontab.tmp

  log INFO "System monitoring setup completed"
}

# ------------------------------------------------------------------------------
# Function: setup_user_environment
# ------------------------------------------------------------------------------
setup_user_environment() {
  log INFO "Setting up user environment for $USERNAME..."

  # Create user if doesn't exist
  if ! id -u "$USERNAME" >/dev/null 2>&1; then
    useradd -m -s /usr/pkg/bin/bash -G wheel "$USERNAME"
    log INFO "User $USERNAME created"
  fi

  # Setup shell configuration
  local shell_config_dir="/home/$USERNAME/.config/shell"
  mkdir -p "$shell_config_dir"

  # Create enhanced .bashrc
  cat > "/home/$USERNAME/.bashrc" << 'EOF'
# Enhanced .bashrc configuration
# ------------------------------

# Environment variables
export EDITOR=vim
export VISUAL=vim
export PAGER=less
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export TERM=xterm-256color

# Enhanced PATH
export PATH="$HOME/.local/bin:$PATH"
export PATH="$HOME/.cargo/bin:$PATH"
export PATH="$HOME/go/bin:$PATH"

# History configuration
HISTSIZE=10000
HISTFILESIZE=20000
HISTCONTROL=ignoreboth
HISTIGNORE="ls:cd:pwd:exit:date:* --help"

# Shell options
shopt -s checkwinsize
shopt -s histappend
shopt -s globstar 2>/dev/null

# Aliases
alias ll='ls -lah'
alias la='ls -A'
alias l='ls -CF'
alias ..='cd ..'
alias ...='cd ../..'
alias grep='grep --color=auto'
alias df='df -h'
alias du='du -h'
alias free='top -o res'
alias ps='ps aux'
alias vim='vim -p'
alias serve='python3 -m http.server'
alias tree='tree -C'
alias ports='netstat -tulanp'

# Enhanced prompt
if [ -x /usr/bin/tput ] && tput setaf 1 >&/dev/null; then
    PS1='\[\033[01;32m\]\u@\h\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ '
else
    PS1='\u@\h:\w\$ '
fi

# Function to create directory and cd into it
mkcd() {
    mkdir -p "$1" && cd "$1"
}

# Function to extract various archive types
extract() {
    if [ -f "$1" ]; then
        case "$1" in
            *.tar.bz2)   tar xjf "$1"   ;;
            *.tar.gz)    tar xzf "$1"   ;;
            *.bz2)       bunzip2 "$1"   ;;
            *.rar)       unrar x "$1"   ;;
            *.gz)        gunzip "$1"    ;;
            *.tar)       tar xf "$1"    ;;
            *.tbz2)      tar xjf "$1"   ;;
            *.tgz)       tar xzf "$1"   ;;
            *.zip)       unzip "$1"     ;;
            *.Z)         uncompress "$1" ;;
            *.7z)        7z x "$1"      ;;
            *)          echo "'$1' cannot be extracted via extract()" ;;
        esac
    else
        echo "'$1' is not a valid file"
    fi
}

# Function to show system information
sysinfo() {
    echo "System Information:"
    echo "------------------"
    uname -a
    echo ""
    uptime
    echo ""
    df -h
    echo ""
    top -l 1 | head -n 10
}

# Load custom configurations
if [ -d "$HOME/.config/shell/conf.d" ]; then
    for f in "$HOME/.config/shell/conf.d"/*.sh; do
        [ -f "$f" ] && . "$f"
    done
fi
EOF

  # Create vim configuration
  mkdir -p "/home/$USERNAME/.vim/"{bundle,colors,ftplugin}
  cat > "/home/$USERNAME/.vimrc" << 'EOF'
" Enhanced Vim Configuration
" ------------------------

" General Settings
set nocompatible
filetype plugin indent on
syntax on
set number
set relativenumber
set ruler
set wrap
set linebreak
set showmatch
set visualbell
set hlsearch
set incsearch
set ignorecase
set smartcase
set expandtab
set smarttab
set shiftwidth=4
set tabstop=4
set autoindent
set smartindent
set history=1000
set undolevels=1000
set wildmenu
set wildmode=list:longest
set wildignore=*.swp,*.bak,*.pyc,*.class
set title
set showmode
set showcmd
set mouse=a
set encoding=utf-8
set scrolloff=3
set sidescrolloff=5
set laststatus=2
set confirm
set backup
set backupdir=~/.vim/backup//
set directory=~/.vim/swap//
set undodir=~/.vim/undo//

" Key Mappings
let mapleader = ","
nnoremap <leader>w :w<CR>
nnoremap <leader>q :q<CR>
nnoremap <leader>x :x<CR>
nnoremap <leader>ev :vsplit $MYVIMRC<cr>
nnoremap <leader>sv :source $MYVIMRC<cr>
nnoremap <leader>l :set list!<CR>
nnoremap <C-h> <C-w>h
nnoremap <C-j> <C-w>j
nnoremap <C-k> <C-w>k
nnoremap <C-l> <C-w>l

" Auto Commands
augroup vimrc_autocmds
    autocmd!
    " Return to last edit position when opening files
    autocmd BufReadPost *
         \ if line("'\"") > 0 && line("'\"") <= line("$") |
         \   exe "normal! g`\"" |
         \ endif
    " Auto-reload vimrc
    autocmd BufWritePost .vimrc source $MYVIMRC
augroup END

" File Type Specific Settings
autocmd FileType python setlocal expandtab shiftwidth=4 tabstop=4
autocmd FileType html setlocal expandtab shiftwidth=2 tabstop=2
autocmd FileType javascript setlocal expandtab shiftwidth=2 tabstop=2
autocmd FileType markdown setlocal wrap linebreak nolist textwidth=0 wrapmargin=0
EOF

  # Create tmux configuration
  cat > "/home/$USERNAME/.tmux.conf" << 'EOF'
# Enhanced tmux Configuration
# -------------------------

# General Settings
set -g default-terminal "screen-256color"
set -g history-limit 10000
set -g base-index 1
setw -g pane-base-index 1
set -g renumber-windows on
set -g set-titles on
set -g mouse on

# Key Bindings
unbind C-b
set -g prefix C-a
bind C-a send-prefix

# Split panes using | and -
bind | split-window -h
bind - split-window -v
unbind '"'
unbind %

# Reload config file
bind r source-file ~/.tmux.conf \; display "Config reloaded!"

# Switch panes using Alt-arrow without prefix
bind -n M-Left select-pane -L
bind -n M-Right select-pane -R
bind -n M-Up select-pane -U
bind -n M-Down select-pane -D

# Status Bar
set -g status-position bottom
set -g status-style bg=colour234,fg=colour137
set -g status-left ''
set -g status-right '#[fg=colour233,bg=colour241,bold] %d/%m #[fg=colour233,bg=colour245,bold] %H:%M:%S '
set -g status-right-length 50
set -g status-left-length 20
EOF

  # Set correct permissions
  chown -R "$USERNAME:$USERNAME" "/home/$USERNAME"
  chmod 700 "/home/$USERNAME/.ssh" 2>/dev/null || true

  log INFO "User environment setup completed"
}

# ------------------------------------------------------------------------------
# Function: main
# ------------------------------------------------------------------------------
main() {
  setup_trap_handlers
  check_requirements
  parse_arguments "$@"

  log INFO "Starting NetBSD system configuration (v${SCRIPT_VERSION})"
  
  enhanced_backup_system
  harden_system
  enhanced_configure_ssh
  configure_development_environment
  setup_monitoring
  setup_user_environment

  log INFO "Configuration completed successfully"
  
  # Print system status
  log INFO "Final system status:"
  log INFO "- Uptime: $(uptime)"
  log INFO "- Disk usage: $(df -h / | tail -n1)"
  log INFO "- Memory: $(vmstat 1 2 | tail -n1)"
  log INFO "- Network interfaces: $(ifconfig | grep -E '^[a-z]' | cut -d: -f1)"
  
  log INFO "Script execution completed successfully"
}

# Execute main function if script is run directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi