#!/bin/sh
# -----------------------------------------------------------------------------
# NetBSD Comprehensive Configuration and Hardening Script
# -----------------------------------------------------------------------------
# Description:
#   This Ash script automates the full configuration of a fresh NetBSD 
#   installation. It is designed to enhance development capabilities, enforce 
#   security best practices, and optimize system performance.
#
# Key Capabilities:
#   • Establishes a modern development environment (Neovim, Zsh, and more)
#   • Implements robust system hardening and security policies
#   • Tunes kernel and network parameters for peak performance
#   • Sets up automated regular backup routines
#   • Configures a comprehensive system monitoring and health-check framework
#   • Prepares containerization, testing, and development environments
#
# Execution:
#   Run this script as the root user to automatically apply all configurations.
#   It features detailed logging, error handling, and step-by-step progress 
#   reporting to ensure a seamless setup.
#
# Note:
#   The script exits immediately on any error and treats unset variables as
#   errors to maintain stability and prevent misconfiguration.
# -----------------------------------------------------------------------------
set -eu

# -----------------------------------------------------------------------------
# Configuration Variables
# -----------------------------------------------------------------------------
LOG_FILE="/var/log/setup.log"
USERNAME="sawyer"
BACKUP_DIR="/var/backups"
SYSCTL_CONF="/etc/sysctl.conf"
PF_CONF="/etc/pf.conf"
MONITORING_DIR="/var/monitoring"

# -----------------------------------------------------------------------------
# Error Handling Configuration
# -----------------------------------------------------------------------------
ERROR_LOG_DIR="/var/log/system-errors"
ERROR_LOG="${ERROR_LOG_DIR}/errors.log"
ERROR_LOG_MAX_SIZE=$((10 * 1024 * 1024))  # 10 MB maximum size for error log

# -----------------------------------------------------------------------------
# Package Management Options
# -----------------------------------------------------------------------------
# Enable automatic dependency resolution for package installations
PKG_OPTIONS="automatic-dependency=yes"

# Set the preferred package mirror path
PKG_PATH="http://cdn.NetBSD.org/pub/pkgsrc/packages/NetBSD/amd64/10.1/All"

# -----------------------------------------------------------------------------
# Advanced Error Handling and Diagnostics System
# -----------------------------------------------------------------------------

# Initialize error handling system
init_error_handling() {
    # Create error logging directory with secure permissions
    ERROR_LOG_DIR="/var/log/system-errors"
    if ! mkdir -p "$ERROR_LOG_DIR"; then
        printf "CRITICAL: Failed to create error log directory\n" >&2
        exit 1
    fi
    chmod 750 "$ERROR_LOG_DIR"

    # Create rotating error log
    ERROR_LOG="${ERROR_LOG_DIR}/errors.log"
    touch "$ERROR_LOG" || exit 1
    chmod 640 "$ERROR_LOG"

    # Maximum size for error log (10MB)
    ERROR_LOG_MAX_SIZE=$((10 * 1024 * 1024))
}

# Function to rotate error log if it gets too large
rotate_error_log() {
    if [ -f "$ERROR_LOG" ]; then
        _size=$(stat -f %z "$ERROR_LOG" 2>/dev/null || echo 0)
        if [ "$_size" -gt "$ERROR_LOG_MAX_SIZE" ]; then
            _timestamp=$(date +%Y%m%d_%H%M%S)
            mv "$ERROR_LOG" "${ERROR_LOG}.${_timestamp}"
            touch "$ERROR_LOG"
            chmod 640 "$ERROR_LOG"

            # Remove old logs (keep last 5)
            ls -t "${ERROR_LOG}".* 2>/dev/null | tail -n +6 | xargs rm -f
        fi
    fi
}

# Function to capture system state
capture_system_state() {
    _error_id="$1"
    _state_file="${ERROR_LOG_DIR}/state_${_error_id}.log"

    {
        echo "System State Snapshot (Error ID: $_error_id)"
        echo "----------------------------------------"
        echo "Timestamp: $(date)"
        echo "Hostname: $(hostname)"
        echo "Kernel: $(uname -v)"
        echo "Uptime: $(uptime)"

        echo "\nMemory Status:"
        vmstat

        echo "\nProcess Status:"
        ps -auxww

        echo "\nFile Descriptor Status:"
        ulimit -a

        echo "\nNetwork Connections:"
        netstat -an

        echo "\nLast 10 System Messages:"
        tail -n 10 /var/log/messages

        echo "\nMount Points:"
        df -h

        echo "\nOpen Files:"
        lsof 2>/dev/null

    } > "$_state_file"
}

# Function to generate unique error ID
generate_error_id() {
    printf "%s_%s_%s" "$(date +%Y%m%d_%H%M%S)" "$(hostname)" "$(dd if=/dev/urandom bs=4 count=1 2>/dev/null | od -An -tx1 | tr -d ' \n')"
}

# Function to format stack trace
format_stack_trace() {
    _pid=$$
    _error_id="$1"
    _line_no="$2"
    _cmd="$3"

    {
        echo "Stack Trace (Error ID: $_error_id)"
        echo "----------------------------------------"
        echo "Process ID: $_pid"
        echo "Command: $_cmd"
        echo "Exit Code: ${4:-Unknown}"
        echo "Line Number: $_line_no"
        echo "Script: $0"
        echo "Current Directory: $(pwd)"
        echo "User: $(id -un)"
        echo "Time: $(date)"

        # Generate stack trace
        _frame=0
        echo "\nCall Stack:"
        while caller $_frame >/dev/null 2>&1; do
            caller $_frame | awk '{
                printf "  [Frame %d] Line %d in function %s (File: %s)\n",
                       NR, $1, $2, $3
            }'
            _frame=$((_frame + 1))
        done

        # Show environment variables
        echo "\nEnvironment Variables:"
        env | sort

        # Show script fragment around error
        if [ -f "$0" ]; then
            echo "\nCode Context:"
            _start=$((_line_no - 5))
            [ $_start -lt 1 ] && _start=1
            _end=$((_line_no + 5))
            sed -n "${_start},${_end}p" "$0" | awk '{
                printf "%s%d%s %s\n",
                       NR == ENVIRON["_line_no"] ? ">" : " ",
                       NR,
                       NR == ENVIRON["_line_no"] ? "*" : " ",
                       $0
            }' "_line_no=$_line_no"
        fi

    } >> "$ERROR_LOG"
}

# Main error handler function
handle_error() {
    _line_no="$1"
    _cmd="$2"
    _exit_code="$3"

    # Generate unique error ID for tracking
    _error_id=$(generate_error_id)

    # Rotate log if needed
    rotate_error_log

    # Log the error
    log_error "Error occurred [ID: $_error_id] in command '$_cmd' at line $_line_no (Exit Code: $_exit_code)"

    # Format and save stack trace
    format_stack_trace "$_error_id" "$_line_no" "$_cmd" "$_exit_code"

    # Capture system state
    capture_system_state "$_error_id"

    # Attempt recovery based on error type
    case "$_cmd" in
        *pkg_add*)
            log_warn "Package installation failed, attempting cleanup..."
            pkg_delete -f "${_cmd##* }" 2>/dev/null
            ;;
        *mount*)
            log_warn "Mount operation failed, checking filesystem..."
            fsck -y "${_cmd##* }" 2>/dev/null
            ;;
        *rm*|*mv*|*cp*)
            log_warn "File operation failed, checking permissions..."
            ls -la "${_cmd##* }" 2>/dev/null
            ;;
    esac

    # Check for critical system states
    _mem_free=$(vmstat | awk 'NR==3{print $4}')
    _disk_free=$(df -k / | awk 'NR==2{print $4}')

    if [ "$_mem_free" -lt 1024 ] || [ "$_disk_free" -lt 102400 ]; then
        log_error "CRITICAL: System resources critically low!"
        echo "Emergency system state saved to ${ERROR_LOG_DIR}/emergency_${_error_id}.state"
        capture_system_state "emergency_${_error_id}"
    fi

    # Notify administrator
    if [ -x /usr/bin/mail ]; then
        {
            echo "Error occurred in system configuration script"
            echo "Error ID: $_error_id"
            echo "Command: $_cmd"
            echo "Line: $_line_no"
            echo "Time: $(date)"
            echo "\nPlease check $ERROR_LOG for complete details"
        } | mail -s "System Configuration Error on $(hostname)" root
    fi

    # Set exit code
    exit "${_exit_code:-1}"
}

# Initialize error handling
init_error_handling

# Set up error trap
trap 'handle_error ${LINENO} "$_" "$?"' ERR

# -----------------------------------------------------------------------------
# Enhanced Logging System
# Provides structured logging with timestamps, levels, and fallback handling
# -----------------------------------------------------------------------------

# Define log levels with severity numbers for filtering
LOG_LEVEL_DEBUG=10
LOG_LEVEL_INFO=20
LOG_LEVEL_WARN=30
LOG_LEVEL_ERROR=40

# Set default minimum log level (can be overridden)
: "${MIN_LOG_LEVEL:=$LOG_LEVEL_INFO}"

# Internal function to get numeric level from string
_get_log_level() {
    local level_str="$1"
    case "$level_str" in
        DEBUG) echo "$LOG_LEVEL_DEBUG" ;;
        INFO)  echo "$LOG_LEVEL_INFO" ;;
        WARN)  echo "$LOG_LEVEL_WARN" ;;
        ERROR) echo "$LOG_LEVEL_ERROR" ;;
        *)     echo "$LOG_LEVEL_INFO" ;;  # Default to INFO for unknown levels
    esac
}

# Internal function to format timestamps consistently
_get_timestamp() {
    date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || \
    date '+%s' 2>/dev/null || \
    echo "TIMESTAMP_ERROR"
}

# Main logging function with enhanced error handling
log() {
    # Validate input
    if [ "$#" -lt 2 ]; then
        printf '[%s] [ERROR] Invalid log call: insufficient arguments\n' "$(_get_timestamp)" >&2
        return 1
    fi

    local _level _level_num _min_level_num _timestamp _log_dir
    _level="$1"
    shift

    _level_num="$(_get_log_level "$_level")"
    _min_level_num="$(_get_log_level "${MIN_LOG_LEVEL:-INFO}")"

    # Check if the message level meets the current log threshold
    if [ "$_level_num" -ge "$_min_level_num" ]; then
        _timestamp="$(_get_timestamp)"

        if [ -n "${LOG_FILE:-}" ]; then
            _log_dir="$(dirname "$LOG_FILE")"
            if ! mkdir -p "$_log_dir" 2>/dev/null; then
                printf '[%s] [ERROR] Failed to create log directory: %s\n' "$_timestamp" "$_log_dir" >&2
                return 1
            fi

            if ! printf '[%s] [%s] %s\n' "$_timestamp" "$_level" "$*" | tee -a "$LOG_FILE" 2>/dev/null; then
                printf '[%s] [%s] %s\n' "$_timestamp" "$_level" "$*" >&2
                printf '[%s] [ERROR] Failed to write to log file: %s\n' "$_timestamp" "$LOG_FILE" >&2
                return 1
            fi
        else
            printf '[%s] [%s] %s\n' "$_timestamp" "$_level" "$*"
        fi
    fi
    return 0
}

# Wrapper functions for different log levels
log_debug() {
    log "DEBUG" "$@"
}

log_info() {
    log "INFO" "$@"
}

log_warn() {
    log "WARN" "$@"
}

log_error() {
    log "ERROR" "$@"
}

# Function to set minimum log level
set_log_level() {
    case "$1" in
        DEBUG|INFO|WARN|ERROR)
            MIN_LOG_LEVEL="$1"
            log_info "Log level set to $1"
            ;;
        *)
            log_error "Invalid log level: $1. Using default (INFO)"
            MIN_LOG_LEVEL="INFO"
            ;;
    esac
}

# -----------------------------------------------------------------------------
# Package Management Configuration
# -----------------------------------------------------------------------------

# Use a heredoc with a temporary file to store package list
# This avoids Bash-specific array constructs while maintaining readability
create_package_list() {
    _tmp_packages=$(mktemp) || {
        log_error "Failed to create temporary package file"
        return 1
    }

    # Write package list using here document
    # The leading tab is important for proper heredoc operation
    cat > "$_tmp_packages" << 'END_PACKAGES'
# Core Development Tools
devel/git                 # Modern distributed version control system
devel/git-base           # Core git tools
devel/git-docs           # Git documentation
lang/gcc10               # GNU Compiler Collection (GCC) version 10
lang/clang              # LLVM C/C++/Objective-C compiler
devel/llvm              # Low Level Virtual Machine compiler infrastructure
devel/gdb               # GNU Debugger
devel/lldb              # Next generation debugger
devel/cmake             # Cross-platform make system
devel/ninja-build       # Small build system
devel/bmake            # NetBSD make
devel/autoconf          # Generate configuration scripts
devel/automake         # GNU Standards-compliant Makefile generator
devel/libtool          # Generic shared library support script
devel/pkgconf          # Package compiler and linker metadata toolkit
devel/ccache           # Compiler cache

# Development Libraries
devel/boost-libs       # Free portable C++ libraries
devel/boost-headers    # Boost C++ headers
devel/ncurses         # CRT screen handling package
devel/readline        # GNU library for editing command lines
devel/gettext         # Tools for multi-lingual messages
devel/zlib            # General purpose compression library
security/openssl      # Secure Socket Layer toolkit

# Editors and Development Environments
editors/vim           # Vim text editor
editors/neovim        # Modern Vim-based text editor
devel/ctags           # Code indexing and navigation tool
devel/cscope         # Source code browser

# Shell and Terminal Tools
shells/zsh            # Z shell with improvements
misc/tmux             # Terminal multiplexer
shells/bash           # GNU Bourne Again Shell
misc/screen          # Multi-screen window manager

# Testing and Debug Tools
devel/gdb             # GNU source-level debugger
devel/valgrind        # Dynamic analysis tools
devel/cgdb           # Curses-based interface to GDB

# Security Tools
security/gnupg2       # GNU Privacy Guard
security/aide         # Advanced Intrusion Detection Environment
security/sudo         # Execute commands as superuser
END_PACKAGES

    echo "$_tmp_packages"
}

# Function to process and install packages
install_packages() {
    log_info "Starting package installation process..."

    # Get temporary package list file
    _pkg_list=$(create_package_list)
    if [ -z "$_pkg_list" ] || [ ! -f "$_pkg_list" ]; then
        log_error "Failed to create package list"
        return 1
    }

    # Cleanup handler for temporary file
    trap 'rm -f "$_pkg_list"' EXIT

    # Initialize counters using portable arithmetic
    _total=0
    _success=0
    _failed=0
    _skipped=0

    # Create temporary files for tracking package status
    _tmp_dir=$(mktemp -d) || {
        log_error "Failed to create temporary directory"
        return 1
    }

    _success_list="${_tmp_dir}/success"
    _failed_list="${_tmp_dir}/failed"
    _skipped_list="${_tmp_dir}/skipped"

    touch "$_success_list" "$_failed_list" "$_skipped_list"

    # Process each package
    while read -r _line; do
        # Skip comments and empty lines
        case "$_line" in
            ''|'#'*) continue ;;
        esac

        # Extract package name (everything before the first '#' or space)
        _package=$(echo "$_line" | sed 's/[[:space:]].*$//' | sed 's/#.*$//')
        [ -z "$_package" ] && continue

        _total=$((_total + 1))

        log_info "Processing package: $_package"

        # Check if package is already installed
        if pkg_info -e "$_package" >/dev/null 2>&1; then
            log_info "Package $_package is already installed"
            echo "$_package" >> "$_skipped_list"
            _skipped=$((_skipped + 1))
            continue
        fi

        # Attempt installation with conflict resolution
        if ! pkg_add -U "$_package" >/dev/null 2>&1; then
            if pkg_info -e "$_package" >/dev/null 2>&1; then
                log_warn "Package conflict detected for $_package, attempting resolution"
                if pkg_delete -f "$_package" >/dev/null 2>&1 && \
                   pkg_add -U "$_package" >/dev/null 2>&1; then
                    log_info "Successfully resolved conflict and installed $_package"
                    echo "$_package" >> "$_success_list"
                    _success=$((_success + 1))
                    continue
                fi
            fi
            log_error "Failed to install $_package"
            echo "$_package" >> "$_failed_list"
            _failed=$((_failed + 1))

            # Check if this is a critical package
            case "$_package" in
                openssl|nginx|pkg-config|gcc|clang)
                    log_error "Critical package $_package failed to install. Aborting."
                    return 1
                    ;;
            esac
        else
            log_info "Successfully installed $_package"
            echo "$_package" >> "$_success_list"
            _success=$((_success + 1))
        fi
    done < "$_pkg_list"

    # Generate installation report
    {
        echo "Package Installation Report"
        echo "=========================="
        echo "Total packages processed: $_total"
        echo "Successfully installed: $_success"
        echo "Already installed (skipped): $_skipped"
        echo "Failed installations: $_failed"

        if [ "$_failed" -gt 0 ]; then
            echo "Failed packages:"
            cat "$_failed_list"
        fi

        if [ "$_success" -gt 0 ]; then
            echo "Newly installed packages:"
            cat "$_success_list"
        fi
    } > "$LOG_FILE.pkg_report"

    # Cleanup temporary directory
    rm -rf "$_tmp_dir"

    log_info "Package installation completed. See $LOG_FILE.pkg_report for details"

    # Determine overall success
    if [ "$_failed" -eq 0 ]; then
        return 0
    elif [ "$_success" -gt "$((_total * 90 / 100))" ]; then
        log_warn "Installation completed with some failures"
        return 0
    else
        log_error "Too many package installation failures"
        return 1
    fi
}

configure_system_performance() {
    log_info "Beginning comprehensive system performance configuration..."

    # First, gather system information and calculate optimal values
    get_system_info() {
        # Get physical memory in bytes and convert to MB for easier calculations
        _phys_mem=$(sysctl -n hw.physmem)
        _mem_mb=$((_phys_mem / 1024 / 1024))

        # Get number of CPUs/cores
        _ncpu=$(sysctl -n hw.ncpu)

        # Get CPU architecture and features
        _machine=$(sysctl -n hw.machine)
        _machine_arch=$(sysctl -n hw.machine_arch)

        # Get page size for memory calculations
        _page_size=$(sysctl -n hw.pagesize)

        # Calculate available memory after reserving 20% for system operations
        _usable_mem=$((_mem_mb * 80 / 100))

        log_info "System information gathered: $_ncpu CPUs, $_mem_mb MB RAM"
    }

    # Calculate optimal TCP buffer sizes based on bandwidth-delay product
    calculate_tcp_buffers() {
        # Start with baseline RTT of 100ms and estimate bandwidth
        # Use fio or similar tool to estimate disk bandwidth if available
        _rtt_ms=100
        _bandwidth_mbps=1000  # Conservative estimate for gigabit ethernet

        # Calculate bandwidth-delay product (BDP)
        # BDP = bandwidth * RTT
        _bdp_bytes=$((_bandwidth_mbps * 1024 * 1024 * _rtt_ms / 8000))

        # Set maximum buffer size to 2 * BDP, with a reasonable minimum
        _tcp_buffer_max=$((_bdp_bytes * 2))
        [ $_tcp_buffer_max -lt 2097152 ] && _tcp_buffer_max=2097152

        # Calculate default buffer size as BDP/2
        _tcp_buffer_default=$((_tcp_buffer_max / 4))
    }

    # Calculate optimal kernel memory parameters
    calculate_kernel_memory() {
        # Calculate maximum number of file descriptors based on available memory
        # Rule of thumb: 256 bytes per file descriptor
        _max_files=$((_usable_mem * 1024 * 1024 / 256))

        # Calculate maximum number of processes
        # Rule of thumb: ~1MB per process minimum
        _max_procs=$((_usable_mem / 2))
        [ $_max_procs -gt 32768 ] && _max_procs=32768

        # Calculate shared memory limits
        _shmmax=$((_phys_mem / 2))
        _shmall=$((_shmmax / _page_size))
    }

    # Create temporary file for sysctl configuration
    _tmp_config=$(mktemp) || {
        log_error "Failed to create temporary file"
        return 1
    }

    # Ensure cleanup on exit
    trap 'rm -f "$_tmp_config"' EXIT

    # Gather system information and calculate optimal values
    get_system_info
    calculate_tcp_buffers
    calculate_kernel_memory

    # Write comprehensive system configuration
    cat > "$_tmp_config" << EOF || {
        log_error "Failed to write sysctl configuration"
        return 1
    }
# -----------------------------------------------------------------------------
# NetBSD System Performance Configuration
# Generated: $(date)
# System: $_machine_arch with $_ncpu CPUs and $_mem_mb MB RAM
# -----------------------------------------------------------------------------

# Network Performance Tuning
# -------------------------
# TCP buffer sizes calculated based on bandwidth-delay product
net.inet.tcp.recvbuf_max=$_tcp_buffer_max
net.inet.tcp.sendbuf_max=$_tcp_buffer_max
net.inet.tcp.recvbuf_default=$_tcp_buffer_default
net.inet.tcp.sendbuf_default=$_tcp_buffer_default

# Enable TCP window scaling and timestamps for better performance
net.inet.tcp.rfc1323=1

# TCP connection tuning
net.inet.tcp.init_win=4
net.inet.tcp.mss_ifmtu=1
net.inet.tcp.sack.enable=1
net.inet.tcp.path_mtu_discovery=1

# Memory Management
# ----------------
# Shared memory limits
kern.ipc.shmmax=$_shmmax
kern.ipc.shmall=$_shmall

# File system and I/O tuning
# -------------------------
kern.maxfiles=$_max_files
kern.maxproc=$_max_procs

# Enable asynchronous I/O
kern.aio.max=2048

# VM system tuning
# ---------------
vm.anonmin=10
vm.filemin=10
vm.execmin=5

# When free memory drops below this percentage, start intensive page reclamation
vm.defer_swapspace_pageouts=1
vm.swapencrypt.enable=1

# Buffer cache tuning
# ------------------
kern.bufcache=$((_usable_mem * 20 / 100))
kern.filecache=$((_usable_mem * 40 / 100))

EOF

    # Verify configuration syntax before applying
    if ! sysctl -n kern.hostname >/dev/null 2>&1; then
        log_error "Sysctl appears to be non-functional"
        return 1
    }

    # Back up existing configuration if it exists
    if [ -f "$SYSCTL_CONF" ]; then
        _backup="${SYSCTL_CONF}.$(date +%Y%m%d_%H%M%S)"
        if ! cp "$SYSCTL_CONF" "$_backup"; then
            log_error "Failed to backup existing configuration"
            return 1
        fi
        log_info "Created backup of existing configuration at $_backup"
    fi

    # Move new configuration into place
    if ! mv "$_tmp_config" "$SYSCTL_CONF"; then
        log_error "Failed to install sysctl configuration"
        return 1
    fi

    # Apply settings with error checking
    if ! sysctl -f "$SYSCTL_CONF"; then
        log_error "Failed to apply sysctl settings"
        # Attempt to restore backup if it exists
        if [ -f "$_backup" ]; then
            log_warn "Attempting to restore previous configuration"
            mv "$_backup" "$SYSCTL_CONF"
            sysctl -f "$SYSCTL_CONF"
        fi
        return 1
    fi

    # Verify key settings were applied
    verify_settings() {
        _failed=0
        while read -r _setting _expected; do
            _actual=$(sysctl -n "$_setting" 2>/dev/null)
            if [ "$_actual" != "$_expected" ]; then
                log_warn "Setting $setting not applied correctly: expected $_expected, got $_actual"
                _failed=$((_failed + 1))
            fi
        done << EOF
net.inet.tcp.recvbuf_max $_tcp_buffer_max
net.inet.tcp.sendbuf_max $_tcp_buffer_max
EOF

        return $_failed
    }

    if ! verify_settings; then
        log_warn "Some settings may not have been applied correctly"
    fi

    log_info "System performance configuration completed successfully"
    log_info "It is recommended to monitor system performance and adjust these values as needed"
}

configure_comprehensive_security() {
    log_info "Beginning comprehensive security configuration for NetBSD..."

    # Define critical paths and configuration files
    SECURITY_DIR="/etc/security"
    PF_CONF="/etc/pf.conf"
    SYSCTL_CONF="/etc/sysctl.conf"
    AIDE_CONF="/etc/aide.conf"
    AIDE_DB="/var/lib/aide"
    PERIODIC_DIR="/etc/periodic/security"

    # Create required directories with secure permissions
    for _dir in "$SECURITY_DIR" "$AIDE_DB" "$PERIODIC_DIR"; do
        if ! mkdir -p "$_dir"; then
            log_error "Failed to create directory: $_dir"
            return 1
        fi
        chmod 750 "$_dir"
    done

    # Detect network interfaces for PF configuration
    detect_network_interfaces() {
        # Get the primary external interface
        _ext_if=$(netstat -rn | grep '^default' | awk '{print $7}')
        if [ -z "$_ext_if" ]; then
            log_warn "Could not detect external interface, defaulting to em0"
            _ext_if="em0"
        }
        log_info "Detected external interface: $_ext_if"
        return 0
    }

    # Configure PF with dynamic interface detection and enhanced security
    configure_pf() {
        _tmp_pf=$(mktemp) || return 1

        # Detect network interfaces
        detect_network_interfaces || return 1

        cat > "$_tmp_pf" << EOF
# -----------------------------------------------------------------------------
# NetBSD PF Firewall Configuration
# Generated: $(date)
# -----------------------------------------------------------------------------

# Interface and Network Definitions
ext_if = "$_ext_if"
tcp_services = "{ ssh, http, https }"
icmp_types = "{ echoreq, unreach }"
private_nets = "{ 10/8, 172.16/12, 192.168/16 }"

# Tuning Options
set limit states 100000
set limit src-nodes 50000
set optimization aggressive
set block-policy drop
set fingerprints "/etc/pf.os"
set skip on lo0
set state-policy if-bound
set timeout { tcp.first 120, tcp.established 86400, tcp.closing 60 }

# Queueing for DDoS mitigation
queue rootq on \$ext_if bandwidth 100M max 100M
queue std parent rootq bandwidth 95M min 5M max 100M default

# Traffic Normalization
scrub in on \$ext_if all fragment reassemble min-ttl 15 max-mss 1440
scrub out on \$ext_if all random-id

# Default Policies
block in all
block out all
block quick from <bruteforce>
block quick from <flood>

# Anti-spoofing
antispoof quick for \$ext_if inet

# Outbound Traffic
pass out quick on \$ext_if all modulate state flags S/SA keep state

# Established Connections
pass in quick on \$ext_if proto tcp from any to any modulate state \
    flags S/SA keep state
pass in quick on \$ext_if proto udp from any to any keep state

# Service-specific Rules
pass in on \$ext_if inet proto tcp to any port \$tcp_services \
    flags S/SA keep state \
    (max-src-conn 100, max-src-conn-rate 15/5, \
     overload <flood> flush global)

# SSH Brute-force Protection
table <bruteforce> persist
pass in on \$ext_if inet proto tcp to any port ssh \
    flags S/SA keep state \
    (max-src-conn 5, max-src-conn-rate 3/60, \
     overload <bruteforce> flush global)

# ICMP Control
pass in inet proto icmp all icmp-type \$icmp_types keep state

# Logging
pass log (all) quick on \$ext_if proto tcp from any to any port ssh
EOF

        # Validate and apply PF configuration
        if ! pfctl -nf "$_tmp_pf"; then
            log_error "PF configuration validation failed"
            rm -f "$_tmp_pf"
            return 1
        fi

        # Back up existing configuration
        if [ -f "$PF_CONF" ]; then
            cp "$PF_CONF" "${PF_CONF}.$(date +%Y%m%d_%H%M%S)"
        fi

        # Install new configuration
        mv "$_tmp_pf" "$PF_CONF"
        chmod 600 "$PF_CONF"

        # Enable and load PF
        pfctl -e && pfctl -f "$PF_CONF"
        return $?
    }

    # Configure system security parameters
    configure_sysctl_security() {
        _tmp_sysctl=$(mktemp) || return 1

        # Calculate memory-based security parameters
        _phys_mem=$(sysctl -n hw.physmem)
        _max_proc_ratio=$((_phys_mem / 1048576 / 32))  # 1 proc per 32MB
        [ $_max_proc_ratio -gt 1024 ] && _max_proc_ratio=1024

        cat > "$_tmp_sysctl" << EOF
# -----------------------------------------------------------------------------
# NetBSD Security Sysctl Configuration
# Generated: $(date)
# -----------------------------------------------------------------------------

# Process and Memory Security
kern.maxproc=$_max_proc_ratio
security.bsd.see_other_uids=0
security.bsd.see_other_gids=0
security.bsd.unprivileged_read_msgbuf=0
security.bsd.hardlink_check_uid=1
security.bsd.hardlink_check_gid=1
security.bsd.unprivileged_proc_debug=0

# Network Security Hardening
net.inet.tcp.blackhole=2
net.inet.udp.blackhole=1
net.inet.ip.random_id=1
net.inet.tcp.drop_synfin=1
net.inet.ip.redirect=0
net.inet6.ip6.redirect=0
net.inet.icmp.bmcastecho=0
net.inet6.icmp6.rediraccept=0
net.inet.tcp.always_keepalive=1
net.inet.tcp.msl=7200
net.inet.tcp.syn_cache_limit=100000
net.inet.tcp.synbucketlimit=100

# Memory Protection
vm.pmap.pg_ps_enabled=1
vm.defer_swapspace_pageouts=1
vm.swapencrypt.enable=1
vm.overcommit=0
vm.max_map_count=262144

# Core Security
kern.securelevel=1
kern.sugid_coredump=0
EOF

        if ! mv "$_tmp_sysctl" "$SYSCTL_CONF"; then
            log_error "Failed to install sysctl security configuration"
            rm -f "$_tmp_sysctl"
            return 1
        fi

        # Apply sysctl settings
        sysctl -f "$SYSCTL_CONF"
        return $?
    }

    # Configure AIDE intrusion detection
    configure_aide() {
        _tmp_aide=$(mktemp) || return 1

        cat > "$_tmp_aide" << 'EOF'
# -----------------------------------------------------------------------------
# AIDE Configuration for NetBSD
# -----------------------------------------------------------------------------

# Database configuration
database=file:/var/lib/aide/aide.db
database_out=file:/var/lib/aide/aide.db.new
gzip_dbout=yes
verbose=5

# Monitoring groups with detailed attributes
PERMS = p+i+u+g+acl
CONTENT = sha256+sha512
EVERYTHING = R+a+b+c+d+i+m+n+p+s+u+g+acl+xattrs+sha256+sha512

# Critical system binaries
/bin$ EVERYTHING
/sbin$ EVERYTHING
/usr/bin$ EVERYTHING
/usr/sbin$ EVERYTHING
/usr/lib$ EVERYTHING
/usr/libexec$ EVERYTHING

# System configuration
/etc$ CONTENT+PERMS
!/etc/mtab
!/etc/.*~

# Security-specific files
/etc/passwd CONTENT+PERMS
/etc/master.passwd CONTENT+PERMS
/etc/group CONTENT+PERMS
/etc/spwd.db CONTENT+PERMS
/etc/pwd.db CONTENT+PERMS

# Log files - check permissions only
/var/log$ PERMS
!/var/log/.*
!/var/log/lastlog

# Devices - check permissions and ownership
/dev$ PERMS
EOF

        if ! mv "$_tmp_aide" "$AIDE_CONF"; then
            log_error "Failed to install AIDE configuration"
            rm -f "$_tmp_aide"
            return 1
        fi

        # Initialize AIDE database
        if ! aide --init; then
            log_error "Failed to initialize AIDE database"
            return 1
        fi

        mv "${AIDE_DB}/aide.db.new" "${AIDE_DB}/aide.db"
        chmod 600 "${AIDE_DB}/aide.db"
        return 0
    }

    # Set up periodic security checks
    configure_security_checks() {
        cat > "${PERIODIC_DIR}/daily.local" << 'EOF'
#!/bin/sh
# -----------------------------------------------------------------------------
# Daily Security Audit Script
# -----------------------------------------------------------------------------

LOGDIR="/var/log/security"
mkdir -p "$LOGDIR"
TODAY=$(date +%Y%m%d)
LOG="${LOGDIR}/audit_${TODAY}.log"

{
    echo "Security Audit Report - $(date)"
    echo "================================"

    # AIDE integrity check
    echo "\nFile Integrity Check:"
    aide --check

    # Login Attempts Analysis
    echo "\nFailed Login Attempts:"
    grep "Failed password" /var/log/authlog | \
        awk '{print $1,$2,$3,$11}' | \
        sort | uniq -c | \
        sort -rn | head -10

    # Process Accounting
    echo "\nUnusual Process Activity:"
    ps auxww | awk '$3 > 50.0 || $4 > 50.0'

    # Network Connections
    echo "\nEstablished Network Connections:"
    netstat -an | grep ESTABLISHED

    # File Permission Changes
    echo "\nRecent Permission Changes in /etc:"
    find /etc -type f -mtime -1 -ls

    # Listening Services
    echo "\nListening Services:"
    netstat -an | grep LISTEN

    # Check for SUID/SGID Files
    echo "\nNew SUID/SGID Files:"
    find / -type f \( -perm -4000 -o -perm -2000 \) -mtime -1 -ls 2>/dev/null

} > "$LOG"

# Send report to root if significant findings exist
if grep -q "FAILED\|WARNING\|ERROR" "$LOG"; then
    mail -s "Security Audit Alert - $(hostname)" root < "$LOG"
fi
EOF

        chmod 750 "${PERIODIC_DIR}/daily.local"
    }

    # Execute configuration functions with error handling
    log_info "Configuring PF firewall..."
    if ! configure_pf; then
        log_error "PF configuration failed"
        return 1
    fi

    log_info "Configuring system security parameters..."
    if ! configure_sysctl_security; then
        log_error "Sysctl security configuration failed"
        return 1
    fi

    log_info "Configuring AIDE intrusion detection..."
    if ! configure_aide; then
        log_error "AIDE configuration failed"
        return 1
    fi

    log_info "Setting up security checks..."
    if ! configure_security_checks; then
        log_error "Security checks configuration failed"
        return 1
    fi

    # Verify critical file permissions
    verify_file_permissions() {
        _failed=0
        for _file in \
            /etc/master.passwd \
            /etc/spwd.db \
            "$PF_CONF" \
            "$AIDE_CONF"
        do
            if ! chmod 600 "$_file"; then
                log_error "Failed to set permissions on $_file"
                _failed=$((_failed + 1))
            fi
        done
        return $_failed
    }

    if ! verify_file_permissions; then
        log_warn "Some file permissions could not be set correctly"
    fi

    log_info "Security configuration completed successfully"
    log_info "Please review logs and test security measures before deploying to production"
}

# -----------------------------------------------------------------------------
# Backup Configuration
# -----------------------------------------------------------------------------
setup_backup_system() {
    log_info "Configuring backup system..."

    # Create backup directories
    mkdir -p "$BACKUP_DIR"/{daily,weekly,monthly}
    chmod 700 "$BACKUP_DIR"

    # Create backup script
    cat > "/usr/local/sbin/system-backup" << 'EOF'
#!/bin/sh
DATE=$(date +%Y%m%d)
BACKUP_ROOT="/var/backups"

# Function to create backup
create_backup() {
    local type="$1"
    local dest="$BACKUP_ROOT/$type"

    tar czf "$dest/system-$DATE.tar.gz" \
        --exclude=/proc \
        --exclude=/tmp \
        --exclude=/var/tmp \
        --exclude=/var/backups \
        --exclude=/var/cache \
        /etc /var/db /home

    # Rotate old backups
    find "$dest" -type f -mtime +30 -delete
}

# Create backups
create_backup "daily"
[ "$(date +%u)" = "7" ] && create_backup "weekly"
[ "$(date +%d)" = "01" ] && create_backup "monthly"
EOF

    chmod 700 "/usr/local/sbin/system-backup"

    # Add to daily cron
    echo "0 1 * * * root /usr/local/sbin/system-backup" > /etc/cron.d/system-backup

    log_info "Backup system configured"
}

# -----------------------------------------------------------------------------
# Configure ZSH with modern features while maintaining simplicity
# -----------------------------------------------------------------------------
setup_zsh() {
    log "Setting up ZSH configuration..."

    # Define user home directory for ZSH configuration
    ZSH_CONFIG_DIR="/home/$USERNAME"

    # Create directory structure for ZSH configurations
    mkdir -p "$ZSH_CONFIG_DIR"/.zsh

    # Install zimfw (ZSH framework)
    curl -fsSL https://raw.githubusercontent.com/zimfw/install/master/install.zsh | zsh

    # Create main .zshrc configuration from a placeholder
    cat > "$ZSH_CONFIG_DIR/.zshrc" << 'EOF'
# -----------------------------------------------------------------------------
# ZSH Configuration with Nord Theme
# Inspired by modern shell practices with Nord aesthetics
# Maintains simplicity and ensures compatibility with NetBSD
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Nord Color Palette
# -----------------------------------------------------------------------------
# Define Nord colors using hexadecimal for true color terminals.
# Adjust these if necessary based on your terminal's color support.
typeset -A nord
nord[polar_night_0]="#2E3440"
nord[polar_night_1]="#3B4252"
nord[polar_night_2]="#434C5E"
nord[polar_night_3]="#4C566A"
nord[polar_night_4]="#D8DEE9"
nord[arctic_5]="#E5E9F0"
nord[arctic_6]="#ECEFF4"
nord[blue_8]="#81A1C1"
nord[blue_9]="#88C0D0"
nord[blue_10]="#8FBCBB"
nord[green]="#A3BE8C"
nord[red]="#BF616A"
nord[orange]="#D08770"
nord[yellow]="#EBCB8B"
nord[magenta]="#B48EAD"

# -----------------------------------------------------------------------------
# Core ZSH Settings
# -----------------------------------------------------------------------------
setopt AUTO_CD              # Change directory without 'cd'
setopt EXTENDED_GLOB        # Extended globbing
setopt NOTIFY              # Report status of background jobs immediately
setopt APPEND_HISTORY      # Append to history instead of overwriting
setopt EXTENDED_HISTORY    # Save timestamp and duration
setopt SHARE_HISTORY       # Share history between sessions
setopt HIST_EXPIRE_DUPS_FIRST
setopt HIST_IGNORE_DUPS
setopt HIST_FIND_NO_DUPS
setopt HIST_REDUCE_BLANKS

# -----------------------------------------------------------------------------
# History Configuration
# -----------------------------------------------------------------------------
HISTFILE=~/.zsh_history
HISTSIZE=50000
SAVEHIST=10000

# -----------------------------------------------------------------------------
# Environment Variables
# -----------------------------------------------------------------------------
export EDITOR='nvim'
export VISUAL='nvim'
export PAGER='less'
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export TERM=xterm-256color

# -----------------------------------------------------------------------------
# Path Configuration
# -----------------------------------------------------------------------------
typeset -U path
path=(
    ~/.local/bin
    ~/.cargo/bin
    ~/.npm-global/bin
    $path
)

# -----------------------------------------------------------------------------
# Aliases
# -----------------------------------------------------------------------------
alias ls='ls -F --color=auto'
alias ll='ls -lh'
alias la='ls -lah'
alias grep='grep --color=auto'
alias vi='nvim'
alias vim='nvim'
alias tree='tree -C'
alias dc='cd'
alias ..='cd ..'
alias ...='cd ../..'
alias mkdir='mkdir -p'
alias df='df -h'
alias du='du -h'
alias free='free -m'
alias g='git'
alias ga='git add'
alias gc='git commit'
alias gp='git push'
alias gst='git status'

# -----------------------------------------------------------------------------
# Key Bindings
# -----------------------------------------------------------------------------
bindkey -e  # Use emacs key bindings
bindkey '^[[A' history-substring-search-up
bindkey '^[[B' history-substring-search-down
bindkey '^[[H' beginning-of-line
bindkey '^[[F' end-of-line
bindkey '^[[3~' delete-char
bindkey '^[[1;5C' forward-word
bindkey '^[[1;5D' backward-word

# -----------------------------------------------------------------------------
# Auto Completion
# -----------------------------------------------------------------------------
autoload -Uz compinit
compinit -d ~/.cache/zcompdump
zstyle ':completion:*' menu select
zstyle ':completion:*' matcher-list 'm:{a-zA-Z}={A-Za-z}'
zstyle ':completion:*' list-colors "${(s.:.)LS_COLORS}"
zstyle ':completion:*' verbose yes
zstyle ':completion:*' group-name ''
zstyle ':completion:*:descriptions' format "%F{${nord[green]}}-- %d --%f"

# -----------------------------------------------------------------------------
# Plugin Configuration
# -----------------------------------------------------------------------------
# Source external plugins
source ~/.zsh/zsh-autosuggestions/zsh-autosuggestions.zsh
source ~/.zsh/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh

# -----------------------------------------------------------------------------
# FZF Integration
# -----------------------------------------------------------------------------
[ -f ~/.fzf.zsh ] && source ~/.fzf.zsh

# -----------------------------------------------------------------------------
# Custom Functions
# -----------------------------------------------------------------------------
# Create a directory and cd into it
function mkcd() {
    mkdir -p "$@" && cd "$@"
}

# Enhanced git log with Nord-themed colors
function glog() {
    git log --graph --pretty=format:"%F{${nord[red]}}%h%f - %F{${nord[yellow]} }%d%f %s %F{${nord[green]}}(%cr)%f %F{${nord[blue_8]}}<%an>%f"
}

# Quick find files by pattern
function ff() { find . -name "*$1*" }

# System update shortcut for NetBSD and npm/pip packages
function update() {
    echo "Updating system packages..."
    sudo pkg_add -u
    echo "Updating npm packages..."
    npm update -g
    echo "Updating pip packages..."
    pip3 list --outdated --format=freeze | grep -v '^\-e' | cut -d = -f 1 | xargs -n1 pip3 install -U
}

# -----------------------------------------------------------------------------
# Prompt Configuration
# -----------------------------------------------------------------------------
autoload -Uz vcs_info
precmd() { vcs_info }
zstyle ':vcs_info:git:*' formats "%F{${nord[polar_night_4]}}(%b)%f"

setopt prompt_subst
PROMPT='%F{${nord[blue_8]}}%~%f ${vcs_info_msg_0_} %F{${nord[green]}}➜%f '

# -----------------------------------------------------------------------------
# Load Local Configuration
# -----------------------------------------------------------------------------
[[ -f ~/.zshrc.local ]] && source ~/.zshrc.local
EOF

    # Set appropriate permissions for configuration directories and files
    chown -R "$USERNAME:wheel" "$ZSH_CONFIG_DIR/.zsh"
    chown "$USERNAME:wheel" "$ZSH_CONFIG_DIR/.zshrc"

    # Set ZSH as the default shell for the user
    log "Setting ZSH as default shell for $USERNAME..."
    chsh -s /usr/pkg/bin/zsh "$USERNAME"

    # Create plugins directories and create symlinks to required plugin files
    mkdir -p "$ZSH_CONFIG_DIR/.zsh/zsh-autosuggestions"
    mkdir -p "$ZSH_CONFIG_DIR/.zsh/zsh-syntax-highlighting"
    ln -sf /usr/pkg/share/zsh-autosuggestions/zsh-autosuggestions.zsh "$ZSH_CONFIG_DIR/.zsh/zsh-autosuggestions/"
    ln -sf /usr/pkg/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh "$ZSH_CONFIG_DIR/.zsh/zsh-syntax-highlighting/"
}

# -----------------------------------------------------------------------------
# Configure Neovim with modern features while maintaining simplicity
# -----------------------------------------------------------------------------
setup_neovim() {
    log "Setting up Neovim configuration..."

    # Create Neovim configuration directory structure
    NVIM_CONFIG_DIR="/home/$USERNAME/.config/nvim"
    mkdir -p "$NVIM_CONFIG_DIR"/{lua,plugin}

    # Install packer.nvim (plugin manager)
    PACKER_DIR="/home/$USERNAME/.local/share/nvim/site/pack/packer/start/packer.nvim"
    if [ ! -d "$PACKER_DIR" ]; then
        git clone --depth 1 https://github.com/wbthomason/packer.nvim "$PACKER_DIR"
    fi

    # Create main init.lua configuration
    cat > "$NVIM_CONFIG_DIR/init.lua" << 'EOF'
-- Basic Settings
vim.opt.number = true
vim.opt.relativenumber = true
vim.opt.wrap = false
vim.opt.encoding = 'utf-8'
vim.opt.swapfile = false
vim.opt.backup = false
vim.opt.undodir = vim.fn.expand('~/.vim/undodir')
vim.opt.undofile = true
vim.opt.hlsearch = false
vim.opt.incsearch = true
vim.opt.termguicolors = true
vim.opt.scrolloff = 8
vim.opt.updatetime = 50
vim.opt.colorcolumn = '80'

-- Indentation
vim.opt.tabstop = 4
vim.opt.softtabstop = 4
vim.opt.shiftwidth = 4
vim.opt.expandtab = true
vim.opt.smartindent = true

-- Leader Key
vim.g.mapleader = ' '

-- Plugin Management with Packer
require('packer').startup(function(use)
    use 'wbthomason/packer.nvim'
    use 'nvim-treesitter/nvim-treesitter'
    use 'nvim-lua/plenary.nvim'
    use 'nvim-telescope/telescope.nvim'
    use 'neovim/nvim-lspconfig'
    use 'hrsh7th/nvim-cmp'
    use 'hrsh7th/cmp-nvim-lsp'
    use 'L3MON4D3/LuaSnip'
    use 'sainnhe/gruvbox-material'
    use {
        'nvim-lualine/lualine.nvim',
        requires = { 'nvim-tree/nvim-web-devicons' }
    }
end)

-- Color Scheme
vim.cmd([[
    set background=dark
    let g:gruvbox_material_background = 'hard'
    colorscheme gruvbox-material
]])

-- Treesitter Configuration
require('nvim-treesitter.configs').setup({
    ensure_installed = {
        'c', 'lua', 'vim', 'python', 'javascript',
        'typescript', 'bash', 'markdown'
    },
    highlight = { enable = true },
    indent = { enable = true }
})

-- LSP Configuration
local lspconfig = require('lspconfig')
local capabilities = require('cmp_nvim_lsp').default_capabilities()

-- Setup language servers
lspconfig.pyright.setup({ capabilities = capabilities })
lspconfig.clangd.setup({ capabilities = capabilities })
lspconfig.tsserver.setup({ capabilities = capabilities })

-- Completion Setup
local cmp = require('cmp')
cmp.setup({
    snippet = {
        expand = function(args)
            require('luasnip').lsp_expand(args.body)
        end,
    },
    mapping = cmp.mapping.preset.insert({
        ['<C-b>'] = cmp.mapping.scroll_docs(-4),
        ['<C-f>'] = cmp.mapping.scroll_docs(4),
        ['<C-Space>'] = cmp.mapping.complete(),
        ['<C-e>'] = cmp.mapping.abort(),
        ['<CR>'] = cmp.mapping.confirm({ select = true })
    }),
    sources = cmp.config.sources({
        { name = 'nvim_lsp' },
        { name = 'luasnip' },
    }, {
        { name = 'buffer' },
    })
})

-- Telescope Configuration
local telescope = require('telescope.builtin')
vim.keymap.set('n', '<leader>ff', telescope.find_files, {})
vim.keymap.set('n', '<leader>fg', telescope.live_grep, {})
vim.keymap.set('n', '<leader>fb', telescope.buffers, {})
vim.keymap.set('n', '<leader>fh', telescope.help_tags, {})

-- Status Line
require('lualine').setup({
    options = {
        theme = 'gruvbox-material',
        component_separators = '|',
        section_separators = '',
    }
})

-- Key Mappings
vim.keymap.set('n', '<leader>e', vim.diagnostic.open_float)
vim.keymap.set('n', '[d', vim.diagnostic.goto_prev)
vim.keymap.set('n', ']d', vim.diagnostic.goto_next)
vim.keymap.set('n', '<leader>q', vim.diagnostic.setloclist)

-- LSP key bindings
vim.api.nvim_create_autocmd('LspAttach', {
    group = vim.api.nvim_create_augroup('UserLspConfig', {}),
    callback = function(ev)
        local opts = { buffer = ev.buf }
        vim.keymap.set('n', 'gD', vim.lsp.buf.declaration, opts)
        vim.keymap.set('n', 'gd', vim.lsp.buf.definition, opts)
        vim.keymap.set('n', 'K', vim.lsp.buf.hover, opts)
        vim.keymap.set('n', 'gi', vim.lsp.buf.implementation, opts)
        vim.keymap.set('n', '<C-k>', vim.lsp.buf.signature_help, opts)
        vim.keymap.set('n', '<leader>wa', vim.lsp.buf.add_workspace_folder, opts)
        vim.keymap.set('n', '<leader>wr', vim.lsp.buf.remove_workspace_folder, opts)
        vim.keymap.set('n', '<leader>D', vim.lsp.buf.type_definition, opts)
        vim.keymap.set('n', '<leader>rn', vim.lsp.buf.rename, opts)
        vim.keymap.set({ 'n', 'v' }, '<leader>ca', vim.lsp.buf.code_action, opts)
        vim.keymap.set('n', 'gr', vim.lsp.buf.references, opts)
    end,
})
EOF

    # Set permissions
    chown -R "$USERNAME:wheel" "/home/$USERNAME/.config"
    chown -R "$USERNAME:wheel" "/home/$USERNAME/.local"

    # Create initial plugin installation script
    cat > "/home/$USERNAME/install_nvim_plugins.sh" << 'EOF'
#!/bin/sh
nvim --headless -c 'autocmd User PackerComplete quitall' -c 'PackerSync'
EOF

    chmod +x "/home/$USERNAME/install_nvim_plugins.sh"
    chown "$USERNAME:wheel" "/home/$USERNAME/install_nvim_plugins.sh"
}

# -----------------------------------------------------------------------------
# Network Optimization
# -----------------------------------------------------------------------------
optimize_network() {
    log_info "Optimizing network configuration..."

    # Configure network tuning parameters
    cat >> "$SYSCTL_CONF" << 'EOF'
# Additional network optimizations
net.inet.tcp.rfc1323=1
net.inet.tcp.sack.enable=1
net.inet.tcp.path_mtu_discovery=1
net.inet.tcp.blackhole=2
net.inet.udp.blackhole=1
EOF

    # Apply network optimizations
    sysctl -p

    log_info "Network optimization complete"
}

configure_nginx() {
    log_info "Configuring NGINX web server..."

    # Ensure the required directories exist
    mkdir -p /var/log/nginx
    mkdir -p /etc/nginx/conf.d
    mkdir -p /etc/nginx/sites-available
    mkdir -p /etc/nginx/sites-enabled

    # Create the main NGINX configuration
    cat > "/etc/nginx/nginx.conf" << 'EOF'
user nginx;
worker_processes auto;
pid /var/run/nginx.pid;

# Load dynamic modules
include /etc/nginx/modules/*.conf;

events {
    worker_connections 1024;
    multi_accept on;
}

http {
    # Basic Settings
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;
    server_tokens off;

    # MIME Types
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    # SSL Settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers EECDH+AESGCM:EDH+AESGCM;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    ssl_session_tickets off;

    # Logging Settings
    access_log /var/log/nginx/access.log combined buffer=512k flush=1m;
    error_log /var/log/nginx/error.log warn;

    # Virtual Host Configs
    include /etc/nginx/conf.d/*.conf;
    include /etc/nginx/sites-enabled/*;
}
EOF

    # Create site configuration for dunamismax.com
    cat > "/etc/nginx/sites-available/dunamismax.com" << 'EOF'
# Redirect www to non-www
server {
    listen 80;
    listen [::]:80;
    server_name www.dunamismax.com;
    return 301 https://dunamismax.com$request_uri;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name www.dunamismax.com;

    ssl_certificate /etc/letsencrypt/live/dunamismax.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/dunamismax.com/privkey.pem;

    return 301 https://dunamismax.com$request_uri;
}

# Main website
server {
    listen 80;
    listen [::]:80;
    server_name dunamismax.com;

    # Redirect all HTTP traffic to HTTPS
    location / {
        return 301 https://$server_name$request_uri;
    }

    # Allow ACME challenges for Let's Encrypt
    location /.well-known/acme-challenge/ {
        root /var/www/acme;
        try_files $uri =404;
    }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name dunamismax.com;

    ssl_certificate /etc/letsencrypt/live/dunamismax.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/dunamismax.com/privkey.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options SAMEORIGIN;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";

    root /home/sawyer/github/hugo/dunamismax.com/public;
    index index.html;

    # Deny access to hidden files
    location ~ /\. {
        deny all;
        # Except .well-known for Let's Encrypt
        location ^~ /.well-known/ {
            allow all;
        }
    }

    location / {
        try_files $uri $uri/ =404;
    }

    # Logging
    access_log /var/log/nginx/dunamismax_access.log combined;
    error_log /var/log/nginx/dunamismax_error.log warn;
}
EOF

    # Create configuration for cloud subdomain
    cat > "/etc/nginx/sites-available/cloud.dunamismax.com" << 'EOF'
server {
    listen 80;
    listen [::]:80;
    server_name cloud.dunamismax.com;

    # Redirect all HTTP traffic to HTTPS
    location / {
        return 301 https://$server_name$request_uri;
    }

    # Allow ACME challenges for Let's Encrypt
    location /.well-known/acme-challenge/ {
        root /var/www/acme;
        try_files $uri =404;
    }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name cloud.dunamismax.com;

    ssl_certificate /etc/letsencrypt/live/cloud.dunamismax.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/cloud.dunamismax.com/privkey.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options SAMEORIGIN;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Nextcloud specific headers
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port $server_port;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Timeout settings
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
EOF

    # Create symbolic links to enable sites
    ln -sf /etc/nginx/sites-available/dunamismax.com /etc/nginx/sites-enabled/
    ln -sf /etc/nginx/sites-available/cloud.dunamismax.com /etc/nginx/sites-enabled/

    # Create directory for ACME challenges
    mkdir -p /var/www/acme
    chown -R nginx:nginx /var/www/acme

    # Update PF rules to allow HTTPS and Let's Encrypt
    if ! grep -q "# Allow HTTPS and Let's Encrypt" /etc/pf.conf; then
        cat >> /etc/pf.conf << 'EOF'

# Allow HTTPS and Let's Encrypt
pass in on $ext_if proto tcp to any port { 80, 443 }
EOF
        pfctl -f /etc/pf.conf
    fi

    # Enable and start NGINX service
    if [ -f /etc/rc.conf ]; then
        if ! grep -q "nginx=YES" /etc/rc.conf; then
            echo "nginx=YES" >> /etc/rc.conf
        fi
    else
        echo "nginx=YES" > /etc/rc.conf
    fi

    # Start or restart NGINX
    if /etc/rc.d/nginx status >/dev/null 2>&1; then
        log_info "Restarting NGINX service..."
        /etc/rc.d/nginx restart
    else
        log_info "Starting NGINX service..."
        /etc/rc.d/nginx start
    fi

    log_info "NGINX configuration completed successfully"
}

configure_kernel_development() {
    log_info "Setting up kernel development environment..."

    # Create directory structure for kernel development
    KERNEL_DEV_DIR="/home/${USERNAME}/kernel-dev"
    SRC_DIR="/usr/src"
    TOOLS_DIR="${KERNEL_DEV_DIR}/tools"
    BUILD_DIR="${KERNEL_DEV_DIR}/builds"

    mkdir -p "${KERNEL_DEV_DIR}"/{tools,builds,patches,docs,tests}

    # Set up source code management
    if [ ! -d "${SRC_DIR}" ]; then
        log_info "Fetching NetBSD source tree..."
        cd /usr
        cvs -q -z2 -d anoncvs@anoncvs.NetBSD.org:/cvsroot checkout -P src
    fi

    # Create kernel configuration template
    cat > "${KERNEL_DEV_DIR}/GENERIC.custom" << 'EOF'
#	$NetBSD$
#
# This is a template for a custom kernel configuration
# Derived from GENERIC with development options enabled

include "arch/amd64/conf/std.amd64"
maxusers 64

# Development and debugging options
makeoptions    DEBUG="-g"           # Build kernel with debugging symbols
makeoptions    COPY_SYMTAB=1       # Enable symbol table
options        DEBUG                # Enable kernel debugging
options        DIAGNOSTIC           # Internal consistency checks
options        KTRACE              # System call tracing support
options        LOCKDEBUG           # Debug lock operations
options        SYSCALL_DEBUG       # Debug system calls
options        SYSCTL_DEBUG        # Debug sysctl operations

# Core kernel debugging facilities
options        DDB                 # In-kernel debugger
options        DDB_ONPANIC=1       # Go into DDB on panic
options        DDB_HISTORY_SIZE=512
options        KGDB                # Remote kernel debugging
options        TRAP_FANCY         # Display detailed trap information
options        PRINTF_BUFSIZE=128  # Debugging buffer size

# Memory debugging
options        DIAGNOSTIC          # Memory consistency checks
options        KMEMSTATS          # Collect kernel memory statistics
options        POOL_DIAGNOSTIC     # Enable pool debugging

# Include GENERIC configuration
include "arch/amd64/conf/GENERIC"
EOF

    # Create build helpers and utilities
    cat > "${TOOLS_DIR}/build-kernel" << 'EOF'
#!/bin/sh
# Helper script for building custom kernels

set -e

KERNEL_CONFIG="$1"
BUILD_ID=$(date +%Y%m%d_%H%M%S)
BUILD_DIR="/home/${USERNAME}/kernel-dev/builds/${BUILD_ID}"

if [ -z "$KERNEL_CONFIG" ]; then
    echo "Usage: $0 <kernel-config-file>"
    exit 1
fi

# Create build directory
mkdir -p "${BUILD_DIR}"

# Build the kernel
cd /usr/src
./build.sh -U -u -j$(sysctl -n hw.ncpu) \
    -O "${BUILD_DIR}" \
    -D "${BUILD_DIR}/dest" \
    -T "${BUILD_DIR}/tools" \
    kernel="$KERNEL_CONFIG"

echo "Kernel built successfully in ${BUILD_DIR}"
echo "To install, run: cp ${BUILD_DIR}/dest/netbsd /netbsd"
EOF

    chmod +x "${TOOLS_DIR}/build-kernel"

    # Create kernel debugging tools
    cat > "${TOOLS_DIR}/crash-analyze" << 'EOF'
#!/bin/sh
# Helper script for analyzing kernel crash dumps

DUMP="$1"
KERNEL="$2"

if [ -z "$DUMP" ] || [ -z "$KERNEL" ]; then
    echo "Usage: $0 <crash-dump> <kernel-image>"
    exit 1
fi

kgdb "$KERNEL" "$DUMP" << 'END'
bt
info registers
ps
END
EOF

    chmod +x "${TOOLS_DIR}/crash-analyze"

    # Set up kernel development environment configurations
    cat > "/home/${USERNAME}/.gdbinit" << 'EOF'
# GDB initialization for kernel debugging
set history filename ~/.gdb_history
set history save on
set history size 10000
set history remove-duplicates unlimited

# Kernel-specific macros
define trace_thread
    set $thread = ((struct lwp *)$arg0)->l_proc
    printf "Process %d (%s)\n", $thread->p_pid, $thread->p_comm
    bt
end

# Helper commands for NetBSD kernel debugging
define btall
    set $proc = allproc.lh_first
    while $proc != 0
        set $pid = $proc->p_pid
        set $pname = $proc->p_comm
        printf "\nProcess %d (%s):\n", $pid, $pname
        set $lwp = $proc->p_lwps.lh_first
        while $lwp != 0
            printf "\nLWP %p:\n", $lwp
            set $pmap = $proc->p_vmspace->vm_map.pmap
            if $lwp->l_cpu != 0
                thread $lwp->l_cpu
                bt
            end
            set $lwp = $lwp->l_sibling.le_next
        end
        set $proc = $proc->p_list.le_next
    end
end
EOF

    # Create documentation for kernel development
    cat > "${KERNEL_DEV_DIR}/docs/README.md" << 'EOF'
# NetBSD Kernel Development Environment

This environment is set up for kernel development and debugging on NetBSD.

## Directory Structure

- `tools/`: Development and debugging tools
- `builds/`: Kernel build outputs
- `patches/`: Custom kernel patches
- `docs/`: Documentation
- `tests/`: Kernel test suites

## Common Tasks

### Building a Custom Kernel

1. Copy GENERIC.custom to /usr/src/sys/arch/amd64/conf/CUSTOM
2. Modify the configuration as needed
3. Run: ./tools/build-kernel CUSTOM

### Analyzing Crash Dumps

1. Save the crash dump (typically in /var/crash)
2. Run: ./tools/crash-analyze /var/crash/netbsd.0.core /netbsd

### Kernel Debugging

1. Set up a serial console or remote debugging connection
2. Use the provided .gdbinit configuration
3. Connect with kgdb: gdb /netbsd
EOF

    # Set up testing framework
    cat > "${KERNEL_DEV_DIR}/tests/run-tests" << 'EOF'
#!/bin/sh
# Basic kernel test framework

# Run core kernel tests
/usr/tests/kernel/all

# Run file system tests
/usr/tests/fs/all

# Run network stack tests
/usr/tests/net/all

# Generate report
echo "Test results saved in /var/tmp/ktests-$(date +%Y%m%d)"
EOF

    chmod +x "${KERNEL_DEV_DIR}/tests/run-tests"

    # Set appropriate permissions
    chown -R "${USERNAME}:wheel" "${KERNEL_DEV_DIR}"
    chmod -R 750 "${KERNEL_DEV_DIR}"

    # Add useful shell aliases for kernel development
    cat >> "/home/${USERNAME}/.zshrc" << 'EOF'

# Kernel Development Aliases
alias kconfig='cd /usr/src/sys/arch/$(uname -m)/conf'
alias ksrc='cd /usr/src/sys'
alias kbuild='cd /usr/src && ./build.sh -U kernel=GENERIC'
alias kdump='crashinfo /var/crash/netbsd.*.core'
alias kcov='gcov -o /usr/src/sys/arch/$(uname -m)/compile/GENERIC'
EOF

    # Install additional development tools if not already present
    pkg_add -U \
        gdb \
        ctags \
        cscope \
        ccache \
        gcc \
        lldb \
        valgrind

    log_info "Kernel development environment setup completed"
    log_info "Documentation available in ${KERNEL_DEV_DIR}/docs/README.md"
}

# Container environment directories
create_container_dirs() {
    _base_dir="/usr/local/container-env"
    log_info "Creating container environment directory structure at $_base_dir"

    for _dir in \
        buildenv \
        images \
        compose \
        scripts \
        registry \
        volumes \
        configs \
        templates \
        security
    do
        _target_dir="${_base_dir}/${_dir}"
        if ! mkdir -p "$_target_dir"; then
            log_error "Failed to create container directory: $_target_dir"
            return 1
        fi
        if ! chmod 750 "$_target_dir"; then
            log_error "Failed to set permissions on: $_target_dir"
            return 1
        fi
        log_debug "Created container directory: $_target_dir"
    done
}

# Testing environment directories
create_test_dirs() {
    _base_dir="/usr/local/test-env"
    log_info "Creating test environment directory structure at $_base_dir"

    for _dir in \
        unit \
        integration \
        performance \
        security \
        results \
        scripts \
        templates \
        fixtures
    do
        _target_dir="${_base_dir}/${_dir}"
        if ! mkdir -p "$_target_dir"; then
            log_error "Failed to create test directory: $_target_dir"
            return 1
        fi
        if ! chmod 750 "$_target_dir"; then
            log_error "Failed to set permissions on: $_target_dir"
            return 1
        fi
        log_debug "Created test directory: $_target_dir"
    done
}

# Development environment directories
create_dev_dirs() {
    _base_dir="/home/${USERNAME}/development"
    log_info "Creating development environment directory structure at $_base_dir"

    for _dir in \
        projects \
        toolchains \
        scripts \
        docs \
        build \
        samples \
        libraries \
        environments
    do
        _target_dir="${_base_dir}/${_dir}"
        if ! mkdir -p "$_target_dir"; then
            log_error "Failed to create development directory: $_target_dir"
            return 1
        fi
        if ! chmod 750 "$_target_dir"; then
            log_error "Failed to set permissions on: $_target_dir"
            return 1
        fi
        log_debug "Created development directory: $_target_dir"
    done
}

create_all_directories() {
    log_info "Beginning directory structure creation process"

    # Ensure we have required permissions
    if [ "$(id -u)" -ne 0 ]; then
        log_error "Directory creation requires root privileges"
        return 1
    }

    # Verify USERNAME is set
    if [ -z "${USERNAME:-}" ]; then
        log_error "USERNAME variable is not set"
        return 1
    }

    # Check for available disk space (require at least 100MB)
    _available_space=$(df -k /usr/local | awk 'NR==2 {print $4}')
    if [ "${_available_space:-0}" -lt 102400 ]; then
        log_error "Insufficient disk space available: ${_available_space}K"
        return 1
    }

    # Create parent directories first
    for _parent in \
        /usr/local \
        /home/"${USERNAME}" \
        /var/log
    do
        if ! mkdir -p "$_parent"; then
            log_error "Failed to create parent directory: $_parent"
            return 1
        fi
        log_debug "Ensured parent directory exists: $_parent"
    done

    # Track creation progress
    _created=0
    _failed=0

    # Create container directories
    if create_container_dirs; then
        _created=$((_created + 1))
        log_info "Container directories created successfully"
    else
        _failed=$((_failed + 1))
        log_error "Failed to create container directories"
    fi

    # Create test directories
    if create_test_dirs; then
        _created=$((_created + 1))
        log_info "Test directories created successfully"
    else
        _failed=$((_failed + 1))
        log_error "Failed to create test directories"
    fi

    # Create development directories
    if create_dev_dirs; then
        _created=$((_created + 1))
        log_info "Development directories created successfully"
    else
        _failed=$((_failed + 1))
        log_error "Failed to create development directories"
    fi

    # Set SELinux contexts if SELinux is enabled
    if command -v selinuxenabled >/dev/null 2>&1 && selinuxenabled; then
        log_info "Setting SELinux contexts"
        if ! restorecon -R /usr/local /home/"${USERNAME}"; then
            log_warn "Failed to set SELinux contexts"
        fi
    fi

    # Generate summary report
    log_info "Directory creation summary:"
    log_info "- Successfully created: $_created directory sets"
    log_info "- Failed to create: $_failed directory sets"

    # Check if any operations failed
    if [ "$_failed" -gt 0 ]; then
        log_error "Some directory creation operations failed"
        return 1
    fi

    log_info "All directory structures created successfully"
    return 0
}

monitor_system_health() {
    log_info "Setting up system health monitoring and reporting framework..."

    # Create directory structure for monitoring
    HEALTH_DIR="/var/system-health"
    REPORTS_DIR="${HEALTH_DIR}/reports"
    METRICS_DIR="${HEALTH_DIR}/metrics"
    ALERTS_DIR="${HEALTH_DIR}/alerts"

    mkdir -p "${REPORTS_DIR}" "${METRICS_DIR}" "${ALERTS_DIR}"

    # Create the main health check script
    cat > "${HEALTH_DIR}/health_check.sh" << 'EOF'
#!/bin/sh

# This script performs comprehensive system health checks and generates detailed
# reports. It monitors critical system components and maintains historical data
# for trend analysis.

set -e
set -u

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORT_FILE="/var/system-health/reports/health_${TIMESTAMP}.report"
METRICS_FILE="/var/system-health/metrics/metrics_${TIMESTAMP}.dat"
ALERT_FILE="/var/system-health/alerts/alerts_${TIMESTAMP}.log"

# Function to calculate percentage with proper rounding
calculate_percentage() {
    echo "scale=2; $1 * 100 / $2" | bc
}

# Function to check if a metric exceeds its threshold
check_threshold() {
    local metric="$1"
    local value="$2"
    local threshold="$3"
    local message="$4"

    if [ "$(echo "${value} ${threshold}" | awk '{print ($1 >= $2)}')" = "1" ]; then
        echo "[ALERT] ${message}" >> "${ALERT_FILE}"
        return 1
    fi
    return 0
}

# Begin health check report
{
    echo "NetBSD System Health Report"
    echo "Generated: $(date)"
    echo "Hostname: $(hostname)"
    echo "Kernel: $(uname -v)"
    echo "Uptime: $(uptime)"
    echo "----------------------------------------"

    # CPU Load and Usage Analysis
    echo "\nCPU Status:"
    top -b -n 1 | head -n 5

    # Record CPU metrics
    CPU_IDLE=$(top -b -n 1 | grep "CPU:" | awk '{print $9}' | tr -d '%')
    CPU_USAGE=$(echo "100 - ${CPU_IDLE}" | bc)
    echo "${TIMESTAMP},cpu_usage,${CPU_USAGE}" >> "${METRICS_FILE}"
    check_threshold "cpu" "${CPU_USAGE}" "90" "CPU usage is critically high: ${CPU_USAGE}%"

    # Memory Analysis
    echo "\nMemory Status:"
    vm_stat=$(vmstat -s)
    total_mem=$(echo "${vm_stat}" | grep "pages managed" | awk '{print $1}')
    free_mem=$(echo "${vm_stat}" | grep "pages free" | awk '{print $1}')

    # Calculate memory usage percentage
    MEM_USAGE=$(calculate_percentage $((total_mem - free_mem)) ${total_mem})
    echo "${TIMESTAMP},memory_usage,${MEM_USAGE}" >> "${METRICS_FILE}"
    check_threshold "memory" "${MEM_USAGE}" "95" "Memory usage is critically high: ${MEM_USAGE}%"

    # Disk Space Analysis
    echo "\nDisk Space Status:"
    df -h | grep -v '^Filesystem'

    # Check each mounted filesystem
    df -P | grep -v '^Filesystem' | while read -r line; do
        usage=$(echo "${line}" | awk '{print $5}' | tr -d '%')
        mount=$(echo "${line}" | awk '{print $6}')
        echo "${TIMESTAMP},disk_usage,${usage},${mount}" >> "${METRICS_FILE}"
        check_threshold "disk" "${usage}" "90" "Disk usage critical on ${mount}: ${usage}%"
    done

    # Network Interface Status
    echo "\nNetwork Interface Status:"
    netstat -i | grep -v '^Name'

    # Record network metrics
    netstat -i | grep -v '^Name' | while read -r line; do
        interface=$(echo "${line}" | awk '{print $1}')
        errors=$(echo "${line}" | awk '{print $5 + $7}')
        echo "${TIMESTAMP},network_errors,${errors},${interface}" >> "${METRICS_FILE}"
        check_threshold "network" "${errors}" "100" "High error count on ${interface}: ${errors}"
    done

    # Process Analysis
    echo "\nProcess Status:"
    ps -axwwo pid,pcpu,pmem,rss,command | head -n 10

    # System Service Status
    echo "\nService Status:"
    services="sshd nginx postfix bind monit"
    for service in ${services}; do
        if /etc/rc.d/${service} status > /dev/null 2>&1; then
            echo "${service}: Running"
            echo "${TIMESTAMP},service_status,1,${service}" >> "${METRICS_FILE}"
        else
            echo "${service}: Stopped"
            echo "${TIMESTAMP},service_status,0,${service}" >> "${METRICS_FILE}"
            echo "[ALERT] Service ${service} is not running" >> "${ALERT_FILE}"
        fi
    done

    # Security Checks
    echo "\nSecurity Status:"
    # Check failed login attempts
    failed_logins=$(grep "Failed password" /var/log/authlog | wc -l)
    echo "Failed login attempts: ${failed_logins}"
    echo "${TIMESTAMP},failed_logins,${failed_logins}" >> "${METRICS_FILE}"
    check_threshold "security" "${failed_logins}" "50" "High number of failed logins: ${failed_logins}"

    # Check open ports
    echo "\nOpen Ports:"
    netstat -an | grep LISTEN

    # System Updates Status
    echo "\nSystem Updates Status:"
    pkg_admin fetch-pkg-vulnerabilities > /dev/null 2>&1
    pkg_admin audit

    # Performance Metrics
    echo "\nPerformance Metrics:"
    vmstat 1 5

    # Generate Recommendations
    echo "\nRecommendations:"
    if [ -s "${ALERT_FILE}" ]; then
        echo "Critical issues found:"
        cat "${ALERT_FILE}"
        echo "\nSuggested actions:"
        while read -r alert; do
            case "${alert}" in
                *"CPU usage"*)
                    echo "- Review and optimize running processes"
                    echo "- Consider upgrading CPU resources"
                    ;;
                *"Memory usage"*)
                    echo "- Analyze memory-intensive processes"
                    echo "- Consider increasing swap space"
                    ;;
                *"Disk usage"*)
                    echo "- Clean up unnecessary files"
                    echo "- Consider expanding storage"
                    ;;
                *"Service"*)
                    echo "- Investigate and restart failed services"
                    echo "- Review service logs for errors"
                    ;;
            esac
        done < "${ALERT_FILE}"
    else
        echo "No critical issues found."
    fi

} | tee "${REPORT_FILE}"

# Cleanup old reports (keep last 30 days)
find "${REPORTS_DIR}" -type f -mtime +30 -delete
find "${METRICS_DIR}" -type f -mtime +30 -delete
find "${ALERTS_DIR}" -type f -mtime +30 -delete

# Send alerts if any were generated
if [ -s "${ALERT_FILE}" ]; then
    mail -s "System Health Alerts - $(hostname)" root < "${ALERT_FILE}"
fi
EOF

    chmod +x "${HEALTH_DIR}/health_check.sh"

    # Create a trend analysis script
    cat > "${HEALTH_DIR}/analyze_trends.sh" << 'EOF'
#!/bin/sh

# This script analyzes system health trends over time

METRICS_DIR="/var/system-health/metrics"
DAYS_TO_ANALYZE=30

echo "System Health Trend Analysis"
echo "Last ${DAYS_TO_ANALYZE} days"
echo "----------------------------------------"

# CPU Usage Trends Analysis
echo "CPU Usage Trends:"
if [ -d "${METRICS_DIR}" ]; then
    # Use temporary file for storing grep results
    _cpu_data="/tmp/cpu_analysis.$$"

    # Safely collect CPU data
    grep "cpu_usage" "${METRICS_DIR}"/* > "${_cpu_data}" 2>/dev/null || true

    if [ -s "${_cpu_data}" ]; then
        awk -F',' '
            BEGIN { sum = 0; count = 0; }
            {
                if (NF >= 3 && $3 ~ /^[0-9.]+$/) {
                    sum += $3;
                    count++;
                }
            }
            END {
                if (count > 0) {
                    printf "Average: %.2f%%\n", sum/count;
                } else {
                    print "No valid data found";
                }
            }' "${_cpu_data}"
    else
        echo "No CPU usage data available"
    fi
    rm -f "${_cpu_data}"
else
    echo "Metrics directory not found"
fi

# Memory Usage Trends Analysis
echo "Memory Usage Trends:"
if [ -d "${METRICS_DIR}" ]; then
    # Use temporary file for storing grep results
    _mem_data="/tmp/mem_analysis.$$"

    # Safely collect memory data
    grep "memory_usage" "${METRICS_DIR}"/* > "${_mem_data}" 2>/dev/null || true

    if [ -s "${_mem_data}" ]; then
        awk -F',' '
            BEGIN { sum = 0; count = 0; }
            {
                if (NF >= 3 && $3 ~ /^[0-9.]+$/) {
                    sum += $3;
                    count++;
                }
            }
            END {
                if (count > 0) {
                    printf "Average: %.2f%%\n", sum/count;
                } else {
                    print "No valid data found";
                }
            }' "${_mem_data}"
    else
        echo "No memory usage data available"
    fi
    rm -f "${_mem_data}"
else
    echo "Metrics directory not found"
fi

# Analyze disk usage trends
echo "\nDisk Usage Trends:"
grep "disk_usage" "${METRICS_DIR}"/* | \
    awk -F',' '{
        usage[$4]+=$3;
        count[$4]++
    } END {
        for (fs in usage)
            printf "%s: %.2f%%\n", fs, usage[fs]/count[fs]
    }'

# Analyze service stability
echo "\nService Stability:"
grep "service_status" "${METRICS_DIR}"/* | \
    awk -F',' '{
        uptime[$4]+=($3=="1"?1:0);
        total[$4]++
    } END {
        for (svc in uptime)
            printf "%s: %.2f%%\n", svc, (uptime[svc]/total[svc])*100
    }'
EOF

    chmod +x "${HEALTH_DIR}/analyze_trends.sh"

    # Set up periodic execution via cron
    cat > "/etc/cron.d/system-health" << EOF
# Run health check every hour
0 * * * * root ${HEALTH_DIR}/health_check.sh >/dev/null 2>&1

# Run trend analysis daily
0 0 * * * root ${HEALTH_DIR}/analyze_trends.sh > ${REPORTS_DIR}/daily_trends.report 2>&1
EOF

    # Create a simple web interface for viewing reports
    mkdir -p /var/www/health-reports
    cat > "/var/www/health-reports/index.php" << 'EOF'
<?php
header("Content-Type: text/html; charset=UTF-8");
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>System Health Reports</title>
    <style>
        body { font-family: monospace; margin: 2em; }
        .report { margin: 1em 0; padding: 1em; border: 1px solid #ccc; }
        .alert { color: red; }
    </style>
</head>
<body>
    <h1>System Health Reports</h1>
    <?php
    $reports_dir = '/var/system-health/reports/';
    $files = array_diff(scandir($reports_dir, SCANDIR_SORT_DESCENDING), array('..', '.'));

    foreach ($files as $file) {
        echo "<div class='report'>";
        echo "<h3>$file</h3>";
        echo "<pre>";
        echo htmlspecialchars(file_get_contents($reports_dir . $file));
        echo "</pre>";
        echo "</div>";
    }
    ?>
</body>
</html>
EOF

    # Set appropriate permissions
    chown -R www:www /var/www/health-reports
    chmod -R 750 "${HEALTH_DIR}"

    # Add aliases for quick access to health monitoring
    cat >> "/home/${USERNAME}/.zshrc" << 'EOF'

# System Health Monitoring Aliases
alias health='sudo /var/system-health/health_check.sh'
alias health-trends='sudo /var/system-health/analyze_trends.sh'
alias health-reports='less /var/system-health/reports/$(ls -t /var/system-health/reports | head -1)'
EOF

    log_info "System health monitoring framework has been set up successfully"
    log_info "Health checks will run hourly and trend analysis daily"
    log_info "Reports are available in ${REPORTS_DIR}"
    log_info "Web interface available at http://localhost/health-reports/"
}

configure_container_environment() {
    log_info "Setting up comprehensive container and virtualization development environment..."

    # Create structured directory hierarchy for container development
    create_container_dirs

    # Configure container runtime environment
    cat > "/etc/containers/containers.conf" << 'EOF'
[containers]
# Network configuration
netns="bridge"
network_interface_name="br0"
network_cmd="/usr/sbin/bridge"

# Security settings
userns="host"
ipcns="host"
utsns="private"
cgroupns="host"
cgroups="enabled"

# Logging configuration
log_driver = "k8s-file"
log_size_max = 52428800
log_tag = "{{.Name}}_{{.ID}}"

# Resource management
pids_limit = 2048
memory_limit = "4g"
cpu_shares = 1024

[engine]
# Runtime settings
cgroup_manager = "cgroupfs"
events_logger = "journald"
runtime = "crun"
runtime_path = ["/usr/bin/crun", "/usr/local/bin/crun"]

# Storage configuration
volume_path = "/var/lib/containers/storage/volumes"
image_default_transport = "docker://"
image_volume = "bind"

[network]
# Network configuration details
network_backend = "cni"
cni_plugin_dirs = ["/usr/local/lib/cni"]
default_subnet = "10.88.0.0/16"

EOF

    # Set up local container registry configuration
    cat > "${CONTAINER_BASE}/configs/registry.yml" << 'EOF'
version: 0.1
log:
fields:
    service: registry
storage:
cache:
    blobdescriptor: inmemory
filesystem:
    rootdirectory: /var/lib/registry
http:
addr: :5000
headers:
    X-Content-Type-Options: [nosniff]
health:
storagedriver:
    enabled: true
    interval: 10s
    threshold: 3
EOF

    # Create utility scripts for container management
    cat > "${CONTAINER_BASE}/scripts/build-secure-container" << 'EOF'
#!/bin/sh
# Helper script for building containers with security best practices

set -e
set -u

IMAGE_NAME="$1"
VERSION="${2:-latest}"
CONTEXT_DIR="${3:-.}"

# Security scanning configuration
TRIVY_SEVERITY="HIGH,CRITICAL"
DOCKLE_IGNORE="CIS-DI-0001,CIS-DI-0005,CIS-DI-0006"

# Build the container
buildah build-using-dockerfile \
    --format docker \
    --security-opt seccomp=unconfined \
    --security-opt label=disable \
    --tag "${IMAGE_NAME}:${VERSION}" \
    "${CONTEXT_DIR}"

# Scan the image for vulnerabilities
if command -v trivy >/dev/null 2>&1; then
    echo "Scanning image for vulnerabilities..."
    trivy image --severity "${TRIVY_SEVERITY}" "${IMAGE_NAME}:${VERSION}"
fi

# Check Dockerfile best practices
if command -v dockle >/dev/null 2>&1; then
    echo "Checking Dockerfile best practices..."
    dockle --ignore "${DOCKLE_IGNORE}" "${IMAGE_NAME}:${VERSION}"
fi
EOF
    chmod +x "${CONTAINER_BASE}/scripts/build-secure-container"

    # Create container security policies
    cat > "${CONTAINER_BASE}/security/seccomp.json" << 'EOF'
{
    "defaultAction": "SCMP_ACT_ERRNO",
    "architectures": ["SCMP_ARCH_X86_64"],
    "syscalls": [
        {
            "names": [
                "accept4", "access", "arch_prctl", "bind", "brk",
                "chdir", "chmod", "chown", "close", "connect",
                "dup2", "execve", "exit_group", "faccessat",
                "fchdir", "fchmod", "fchown", "fcntl", "fstat",
                "futex", "getdents64", "getegid", "geteuid",
                "getgid", "getpeername", "getpgrp", "getpid",
                "getppid", "getpriority", "getrandom", "getresgid",
                "getresuid", "getrlimit", "getsockname",
                "getsockopt", "gettid", "gettimeofday", "getuid",
                "io_setup", "ioctl", "kill", "lseek", "lstat",
                "madvise", "mkdir", "mmap", "mprotect", "munmap",
                "nanosleep", "newfstatat", "open", "openat",
                "pipe2", "pread64", "prlimit64", "pselect6",
                "read", "readlink", "readlinkat", "rename",
                "rmdir", "rt_sigaction", "rt_sigprocmask",
                "rt_sigqueueinfo", "rt_sigreturn", "select",
                "sendto", "set_robust_list", "set_tid_address",
                "setgid", "setgroups", "setitimer", "setpgid",
                "setresgid", "setresuid", "setsid", "setsockopt",
                "setuid", "shmat", "shmctl", "shmdt", "shmget",
                "shutdown", "socket", "socketpair", "stat",
                "statfs", "sysinfo", "umask", "uname", "unlink",
                "wait4", "write"
            ],
            "action": "SCMP_ACT_ALLOW"
        }
    ]
}
EOF

    # Set up container networking
    cat > "/etc/rc.d/container-network" << 'EOF'
#!/bin/sh
#
# Container networking service

. /etc/rc.subr

name="container_network"
rcvar="${name}_enable"
start_cmd="${name}_start"
stop_cmd="${name}_stop"

container_network_start()
{
    # Create and configure bridge interface
    /sbin/ifconfig bridge0 create
    /sbin/ifconfig bridge0 inet 10.88.0.1/16
    /sbin/ifconfig bridge0 up

    # Enable IP forwarding
    /sbin/sysctl -w net.inet.ip.forwarding=1
}

container_network_stop()
{
    /sbin/ifconfig bridge0 destroy
}

load_rc_config $name
run_rc_command "$1"
EOF
    chmod +x "/etc/rc.d/container-network"

    # Create helpful aliases for container management
    cat >> "/home/${USERNAME}/.zshrc" << 'EOF'

# Container Management Aliases
alias cb='${CONTAINER_BASE}/scripts/build-secure-container'
alias cps='podman ps --format "table {{.ID}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"'
alias clog='podman logs -f'
alias cex='podman exec -it'
alias ccp='podman cp'
alias cst='podman stats'
alias cin='podman inspect'
alias cprune='podman system prune -a --volumes'
EOF

    # Enable container services in rc.conf
    if [ -f /etc/rc.conf ]; then
        for service in container_network container_registry; do
            if ! grep -q "${service}_enable=\"YES\"" /etc/rc.conf; then
                echo "${service}_enable=\"YES\"" >> /etc/rc.conf
            fi
        done
    fi

    log_info "Container environment setup completed successfully"
    log_info "Container tools and scripts available in ${CONTAINER_BASE}"
    log_info "Run 'source ~/.zshrc' to load new container aliases"
}

configure_testing_environment() {
    log_info "Setting up comprehensive testing environment..."

    # Create structured directory hierarchy for testing
    create_test_dirs

    # Create performance testing configuration file
    cat > "${TEST_BASE}/performance/benchmark.conf" << 'EOF'
# System Performance Test Configuration

# CPU Testing Parameters
cpu_test:
    duration: 600        # Test duration in seconds
    thread_counts:       # Number of threads to test with
        - 1
        - $(( $(sysctl -n hw.ncpu) ))
        - $(( $(sysctl -n hw.ncpu) * 2 ))
    test_types:
        - cpu_fixed_point
        - cpu_floating_point
        - cpu_prime
        - cpu_matrix
        - cpu_encryption

# Memory Testing Parameters
memory_test:
    total_size: 4G      # Total amount of memory to test
    block_sizes:        # Different block sizes to test
        - 4K
        - 64K
        - 1M
        - 16M
    operations:
        - sequential_read
        - sequential_write
        - random_read
        - random_write
    threads: 4          # Number of threads for memory testing

# Disk I/O Testing Parameters
disk_test:
    file_size: 8G       # Size of test file
    block_sizes:
        - 4K
        - 64K
        - 1M
    io_patterns:
        - sequential
        - random
    io_depths:          # Queue depths to test
        - 1
        - 16
        - 32
    filesystems:        # Filesystems to test
        - ffs
        - ext2fs
        - tmpfs

# Network Testing Parameters
network_test:
    protocols:
        - tcp
        - udp
    packet_sizes:
        - 64
        - 1500
        - 9000
    duration: 60        # Test duration in seconds
    parallel: 4         # Number of parallel streams
EOF

    # Create primary test execution script
    cat > "${TEST_BASE}/scripts/run-system-tests" << 'EOF'
#!/bin/sh
# Comprehensive system testing script

set -e
set -u

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="${TEST_BASE}/results/${TIMESTAMP}"
mkdir -p "${RESULTS_DIR}"

log_test() {
    local level="$1"
    shift
    printf "[%s] [%s] %s\n" "$(date '+%Y-%m-%d %H:%M:%S')" "$level" "$*" | \
        tee -a "${RESULTS_DIR}/test.log"
}

# CPU Performance Testing
cpu_performance_test() {
    log_test "INFO" "Starting CPU performance tests"

    sysbench cpu \
        --cpu-max-prime=20000 \
        --threads=4 \
        --time=300 \
        run > "${RESULTS_DIR}/cpu_test.log" 2>&1

    # Extract and format results
    awk '/events per second/ {print "CPU Events/sec:", $4}' \
        "${RESULTS_DIR}/cpu_test.log" >> "${RESULTS_DIR}/summary.txt"
}

# Memory Performance Testing
memory_performance_test() {
    log_test "INFO" "Starting memory performance tests"

    sysbench memory \
        --memory-block-size=1K \
        --memory-total-size=100G \
        --memory-access-mode=seq \
        run > "${RESULTS_DIR}/memory_test.log" 2>&1

    # Extract and format results
    awk '/transferred/ {print "Memory Transfer Rate:", $4, $5}' \
        "${RESULTS_DIR}/memory_test.log" >> "${RESULTS_DIR}/summary.txt"
}

# Disk I/O Performance Testing
disk_performance_test() {
    log_test "INFO" "Starting disk I/O performance tests"

    # Create test file
    TEST_FILE="/tmp/fio_test"

    fio --filename="${TEST_FILE}" \
        --direct=1 \
        --rw=randrw \
        --bs=4k \
        --ioengine=posixaio \
        --iodepth=16 \
        --group_reporting \
        --name=test \
        --size=1G \
        --runtime=60 \
        --numjobs=4 \
        --output="${RESULTS_DIR}/disk_test.log"

    # Clean up test file
    rm -f "${TEST_FILE}"

    # Extract and format results
    awk '/READ/ {print "Disk Read IOPS:", $3}' \
        "${RESULTS_DIR}/disk_test.log" >> "${RESULTS_DIR}/summary.txt"
    awk '/WRITE/ {print "Disk Write IOPS:", $3}' \
        "${RESULTS_DIR}/disk_test.log" >> "${RESULTS_DIR}/summary.txt"
}

# Network Performance Testing
network_performance_test() {
    log_test "INFO" "Starting network performance tests"

    # Start iperf3 server in background
    iperf3 -s -D

    # Run client test
    iperf3 -c localhost \
        -t 30 \
        -P 4 \
        -J > "${RESULTS_DIR}/network_test.json"

    # Stop iperf3 server
    pkill iperf3

    # Extract and format results
    jq -r '.end.sum_received.bits_per_second' "${RESULTS_DIR}/network_test.json" | \
        awk '{print "Network Throughput:", $1/1000000, "Mbps"}' \
        >> "${RESULTS_DIR}/summary.txt"
}

# Run all tests
main() {
    log_test "INFO" "Starting system performance tests"

    # Create results directory
    mkdir -p "${RESULTS_DIR}"

    # Run individual tests
    cpu_performance_test
    memory_performance_test
    disk_performance_test
    network_performance_test

    log_test "INFO" "All tests completed. Results available in ${RESULTS_DIR}"

    # Generate summary report
    {
        echo "System Performance Test Summary"
        echo "=============================="
        echo "Date: $(date)"
        echo "System: $(uname -a)"
        echo "CPU: $(sysctl -n hw.model)"
        echo "Memory: $(sysctl -n hw.physmem | awk '{print $1/1024/1024 "MB"}')"
        echo "=============================="
        cat "${RESULTS_DIR}/summary.txt"
    } | tee "${RESULTS_DIR}/report.txt"
}

# Execute main function
main "$@"
EOF
    chmod +x "${TEST_BASE}/scripts/run-system-tests"

    # Create test data generator script
    cat > "${TEST_BASE}/scripts/generate-test-data" << 'EOF'
#!/bin/sh
# Generate test data for various testing scenarios

set -e
set -u

FIXTURES_DIR="${TEST_BASE}/fixtures"

# Generate random text data
dd if=/dev/urandom bs=1M count=10 | base64 > "${FIXTURES_DIR}/random.txt"

# Generate sample JSON data
cat > "${FIXTURES_DIR}/sample.json" << 'INNER_EOF'
{
    "test_cases": [
        {"id": 1, "name": "basic_test", "expected": "pass"},
        {"id": 2, "name": "edge_case", "expected": "pass"},
        {"id": 3, "name": "error_case", "expected": "fail"}
    ]
}
INNER_EOF

# Generate sample CSV data
cat > "${FIXTURES_DIR}/sample.csv" << 'INNER_EOF'
id,name,value,timestamp
1,test1,100,2024-01-19T10:00:00
2,test2,200,2024-01-19T10:01:00
3,test3,300,2024-01-19T10:02:00
INNER_EOF
EOF
    chmod +x "${TEST_BASE}/scripts/generate-test-data"

    # Add testing aliases to shell configuration
    cat >> "/home/${USERNAME}/.zshrc" << EOF

# Testing Environment Aliases
alias run-tests='${TEST_BASE}/scripts/run-system-tests'
alias gen-testdata='${TEST_BASE}/scripts/generate-test-data'
alias test-report='less \$(ls -t ${TEST_BASE}/results/*/report.txt | head -1)'
EOF

    # Set appropriate permissions
    chown -R "${USERNAME}:wheel" "${TEST_BASE}"

    log_info "Testing environment setup completed successfully"
    log_info "Test scripts available in ${TEST_BASE}/scripts"
    log_info "Run 'source ~/.zshrc' to load new testing aliases"
}

configure_ssh() {
    log_info "Starting SSH configuration with enhanced security settings..."

    # Define configuration paths
    _ssh_config="/etc/ssh/sshd_config"
    _ssh_dir="/etc/ssh"
    _empty_dir="/var/empty/sshd"
    _moduli_file="${_ssh_dir}/moduli"

    # Check for required commands
    for _cmd in ssh-keygen sshd; do
        if ! command -v "$_cmd" >/dev/null 2>&1; then
            log_error "Required command '$_cmd' not found"
            return 1
        fi
    done

    # Ensure SSH directories exist with proper permissions
    for _dir in "$_ssh_dir" "$_empty_dir"; do
        if ! mkdir -p "$_dir"; then
            log_error "Failed to create directory: $_dir"
            return 1
        fi
        chmod 755 "$_dir"
    done

    # Backup existing configuration
    if [ -f "$_ssh_config" ]; then
        _backup="${_ssh_config}.backup.$(date +%Y%m%d)"
        if ! cp "$_ssh_config" "$_backup"; then
            log_error "Failed to create SSH config backup"
            return 1
        fi
        log_info "Created backup of SSH configuration at $_backup"
    fi

    # Generate new host keys with proper error handling
    for _key_type in rsa ed25519; do
        _key_file="${_ssh_dir}/ssh_host_${_key_type}_key"

        # Check if key needs regeneration
        if [ ! -f "$_key_file" ] || [ "$(stat -f %m "$_key_file")" -lt "$(date -v-365d +%s)" ]; then
            log_info "Generating new $_key_type host key..."

            # Remove old keys if they exist
            rm -f "$_key_file" "${_key_file}.pub"

            if ! ssh-keygen -t "$_key_type" -f "$_key_file" -N "" -q; then
                log_error "Failed to generate $_key_type host key"
                return 1
            fi

            # Set proper permissions
            chmod 600 "$_key_file"
            chmod 644 "${_key_file}.pub"
        fi
    done

    # Generate DH moduli if needed
    if [ ! -f "$_moduli_file" ] || [ "$(stat -f %m "$_moduli_file")" -lt "$(date -v-30d +%s)" ]; then
        log_info "Generating new DH moduli (this may take a while)..."

        # Create temporary file for moduli generation
        _tmp_moduli=$(mktemp) || {
            log_error "Failed to create temporary file for moduli generation"
            return 1
        }

        if ! ssh-keygen -M generate -O bits=3072 -o "$_tmp_moduli"; then
            log_error "Failed to generate DH moduli"
            rm -f "$_tmp_moduli"
            return 1
        fi

        if ! ssh-keygen -M screen -f "$_tmp_moduli" -o "$_moduli_file"; then
            log_error "Failed to screen DH moduli"
            rm -f "$_tmp_moduli"
            return 1
        fi

        rm -f "$_tmp_moduli"
        chmod 644 "$_moduli_file"
    fi

    # Create new sshd configuration with secure settings
    _tmp_config=$(mktemp) || {
        log_error "Failed to create temporary config file"
        return 1
    }

    cat > "$_tmp_config" << 'EOF' || {
        log_error "Failed to write SSH configuration"
        rm -f "$_tmp_config"
        return 1
    }
# Security and authentication settings
Protocol 2
HostKey /etc/ssh/ssh_host_ed25519_key
HostKey /etc/ssh/ssh_host_rsa_key

# Authentication methods
PubkeyAuthentication yes
PasswordAuthentication no
PermitRootLogin no
MaxAuthTries 3
AuthenticationMethods publickey

# Access control
AllowUsers sawyer
AllowGroups wheel

# Network settings
AddressFamily inet
Port 22
ListenAddress 0.0.0.0
LoginGraceTime 30
MaxStartups 10:30:100
TCPKeepAlive yes
ClientAliveInterval 300
ClientAliveCountMax 2

# Cryptographic settings
Ciphers chacha20-poly1305@openssh.com,aes256-gcm@openssh.com
MACs hmac-sha2-512-etm@openssh.com,hmac-sha2-256-etm@openssh.com
KexAlgorithms curve25519-sha256@libssh.org,diffie-hellman-group16-sha512

# Security settings
UsePAM yes
X11Forwarding no
AllowTcpForwarding no
PermitTunnel no
PermitUserEnvironment no
EOF

    # Move configuration into place with proper permissions
    if ! mv "$_tmp_config" "$_ssh_config"; then
        log_error "Failed to install SSH configuration"
        rm -f "$_tmp_config"
        return 1
    fi
    chmod 600 "$_ssh_config"

    # Create or update SSH monitoring script
    _monitor_script="/usr/local/sbin/ssh-monitor"
    cat > "$_monitor_script" << 'EOF' || {
        log_error "Failed to create SSH monitoring script"
        return 1
    }
#!/bin/sh
# Monitor SSH connections and record statistics

_log_dir="/var/log/ssh-monitor"
mkdir -p "$_log_dir"

# Record current connections
netstat -an | grep ":22 " > "${_log_dir}/connections.$(date +%Y%m%d)"

# Monitor for potential brute force attempts
_attempts_file="${_log_dir}/failed_attempts.$(date +%Y%m%d)"
grep "Failed password" /var/log/authlog | \
    awk '{print $1,$2,$3,$11}' | sort | uniq -c > "$_attempts_file"

# Alert if there are too many failed attempts
_failed_count=$(wc -l < "$_attempts_file")
if [ "$_failed_count" -gt 100 ]; then
    echo "Warning: High number of failed SSH attempts: $_failed_count" | \
        mail -s "SSH Attack Warning - $(hostname)" root
fi

# Cleanup old logs (keep 30 days)
find "$_log_dir" -type f -mtime +30 -delete
EOF

    chmod 700 "$_monitor_script"

    # Add monitoring to cron if not already present
    if ! grep -q ssh-monitor /etc/cron.d/ssh-monitor 2>/dev/null; then
        echo "0 * * * * root /usr/local/sbin/ssh-monitor" > /etc/cron.d/ssh-monitor
    fi

    # Test configuration before restarting
    if ! sshd -t; then
        log_error "SSH configuration test failed"
        return 1
    fi

    # Restart SSH service
    if ! /etc/rc.d/sshd restart >/dev/null 2>&1; then
        log_error "Failed to restart SSH service"
        return 1
    fi

    log_info "SSH configuration completed successfully"
    log_info "Please test new connection before closing this session"
    return 0
}

    # Create or regenerate DH moduli if needed
    if [ ! -f "$MODULI_FILE" ] || [ "$(stat -f %m "$MODULI_FILE")" -lt "$(date -v-30d +%s)" ]; then
        log_info "Generating new DH moduli (this may take a while)..."
        ssh-keygen -M generate -O bits=3072 -o "${MODULI_FILE}.tmp"
        ssh-keygen -M screen -f "${MODULI_FILE}.tmp" -o "$MODULI_FILE"
        rm -f "${MODULI_FILE}.tmp"
    fi

    # Create new sshd configuration
    cat > "$SSH_CONFIG" << 'EOF'
# Security and authentication settings
Protocol 2
HostKey /etc/ssh/ssh_host_ed25519_key
HostKey /etc/ssh/ssh_host_rsa_key

# Authentication methods
PubkeyAuthentication yes
PasswordAuthentication no
PermitRootLogin no
MaxAuthTries 3
AuthenticationMethods publickey

# Access control
AllowUsers sawyer
AllowGroups wheel

# Network settings
AddressFamily inet
Port 22
ListenAddress 0.0.0.0
LoginGraceTime 30
MaxStartups 10:30:100
TCPKeepAlive yes
ClientAliveInterval 300
ClientAliveCountMax 2

# Cryptographic settings
Ciphers chacha20-poly1305@openssh.com,aes256-gcm@openssh.com,aes128-gcm@openssh.com
MACs hmac-sha2-512-etm@openssh.com,hmac-sha2-256-etm@openssh.com
KexAlgorithms curve25519-sha256@libssh.org,diffie-hellman-group16-sha512,diffie-hellman-group18-sha512

# Logging and monitoring
SyslogFacility AUTH
LogLevel VERBOSE
PrintLastLog yes
PrintMotd no

# Environment and session settings
AcceptEnv LANG LC_*
X11Forwarding no
AllowTcpForwarding no
AllowStreamLocalForwarding no
GatewayPorts no
PermitTunnel no
Banner none
PermitUserEnvironment no
UseDNS no

# SFTP configuration
Subsystem sftp /usr/libexec/sftp-server -f AUTHPRIV -l INFO
EOF

    # Set secure permissions on SSH configuration files
    chmod 600 "$SSH_CONFIG"
    chmod 600 ${SSH_CONFIG_DIR}/ssh_host_*_key
    chmod 644 ${SSH_CONFIG_DIR}/ssh_host_*_key.pub
    chmod 644 "$MODULI_FILE"
    chown -R root:wheel "$SSH_CONFIG_DIR"

    # Create user SSH directory if it doesn't exist
    USER_SSH_DIR="/home/${USERNAME}/.ssh"
    if [ ! -d "$USER_SSH_DIR" ]; then
        mkdir -p "$USER_SSH_DIR"
        chmod 700 "$USER_SSH_DIR"
        chown "${USERNAME}:wheel" "$USER_SSH_DIR"
    fi

    # Generate user SSH key if it doesn't exist
    USER_KEY_FILE="${USER_SSH_DIR}/id_ed25519"
    if [ ! -f "$USER_KEY_FILE" ]; then
        log_info "Generating SSH key for user ${USERNAME}..."
        su - "$USERNAME" -c "ssh-keygen -t ed25519 -f \"$USER_KEY_FILE\" -N \"\""
    fi

    # Set up SSH agent autostart in user's shell configuration
    cat >> "/home/${USERNAME}/.zshrc" << 'EOF'

# SSH Agent Configuration
if [ -z "$SSH_AUTH_SOCK" ]; then
    eval $(ssh-agent -s) > /dev/null
    trap "ssh-agent -k" EXIT
fi
EOF

    # Create ssh-audit script for periodic security checks
    cat > "/usr/local/sbin/ssh-audit" << 'EOF'
#!/bin/sh
# Periodic SSH security audit script

LOG_FILE="/var/log/ssh-audit.log"
CONFIG="/etc/ssh/sshd_config"

{
    echo "SSH Security Audit - $(date)"
    echo "=========================="

    # Check SSH configuration permissions
    echo "\nConfiguration file permissions:"
    ls -l "$CONFIG"

    # Check SSH host keys
    echo "\nHost key permissions:"
    ls -l /etc/ssh/ssh_host_*

    # Check allowed ciphers and algorithms
    echo "\nAllowed ciphers and algorithms:"
    sshd -T | grep -E "^(ciphers|macs|kexalgorithms)"

    # Check recent authentication failures
    echo "\nRecent authentication failures:"
    grep "Failed password" /var/log/authlog | tail -n 5

    # Check for unauthorized access attempts
    echo "\nUnauthorized access attempts:"
    grep "Invalid user" /var/log/authlog | tail -n 5

    echo "\nAudit completed at $(date)"
} > "$LOG_FILE"

# Send report to admin if there are any "Failed password" attempts
if grep -q "Failed password" "$LOG_FILE"; then
    mail -s "SSH Security Audit Report - $(hostname)" root < "$LOG_FILE"
fi
EOF

    chmod 700 "/usr/local/sbin/ssh-audit"

    # Add periodic SSH audit to daily security checks
    echo "30 4 * * * root /usr/local/sbin/ssh-audit" > /etc/cron.d/ssh-audit

    # Create SSH connection monitoring script
    cat > "/usr/local/sbin/ssh-monitor" << 'EOF'
#!/bin/sh
# Monitor SSH connections and record statistics

LOG_DIR="/var/log/ssh-monitor"
mkdir -p "$LOG_DIR"

# Record current connections
netstat -an | grep ":22 " > "$LOG_DIR/connections.$(date +%Y%m%d)"

# Monitor for potential brute force attempts
grep "Failed password" /var/log/authlog | \
    awk '{print $1,$2,$3,$11}' | \
    sort | uniq -c | \
    awk '$1 >= 5' > "$LOG_DIR/potential_attacks.$(date +%Y%m%d)"

# Alert if there are too many failed attempts
FAILED_COUNT=$(grep "Failed password" /var/log/authlog | wc -l)
if [ "$FAILED_COUNT" -gt 100 ]; then
    echo "Warning: High number of failed SSH attempts: $FAILED_COUNT" | \
        mail -s "SSH Attack Warning - $(hostname)" root
fi

# Cleanup old logs (keep 30 days)
find "$LOG_DIR" -type f -mtime +30 -delete
EOF

    chmod 700 "/usr/local/sbin/ssh-monitor"

    # Add SSH monitoring to hourly cron
    echo "0 * * * * root /usr/local/sbin/ssh-monitor" > /etc/cron.d/ssh-monitor

    # Restart SSH service to apply changes
    if /etc/rc.d/sshd restart >/dev/null 2>&1; then
        log_info "SSH configuration completed and service restarted successfully"
    else
        log_error "Failed to restart SSH service"
        return 1
    fi

    log_info "SSH configuration completed. Please test new connection before closing this session."
}

setup_development() {
    log_info "Setting up comprehensive development environment..."

    # Create development directory structure
    create_dev_dirs

    # Set up compiler and toolchain configurations
    cat > "${DEV_BASE}/toolchains/gcc.conf" << 'EOF'
# GCC optimization settings
CFLAGS="-O2 -pipe -march=native"
CXXFLAGS="-O2 -pipe -march=native"
LDFLAGS="-Wl,-O2"
MAKEFLAGS="-j$(sysctl -n hw.ncpu)"
EOF

    cat > "${DEV_BASE}/toolchains/clang.conf" << 'EOF'
# Clang optimization settings
CFLAGS="-O2 -pipe -march=native -flto=thin"
CXXFLAGS="-O2 -pipe -march=native -flto=thin"
LDFLAGS="-Wl,-O2 -flto=thin"
MAKEFLAGS="-j$(sysctl -n hw.ncpu)"
EOF

    # Create development environment loader script
    cat > "${DEV_BASE}/scripts/dev-env.sh" << 'EOF'
#!/bin/sh
# Development environment configuration loader

# Source the appropriate toolchain configuration
load_toolchain() {
    local compiler="$1"
    local config_file="${DEV_BASE}/toolchains/${compiler}.conf"

    if [ -f "$config_file" ]; then
        . "$config_file"
        export CFLAGS CXXFLAGS LDFLAGS MAKEFLAGS
        echo "Loaded ${compiler} toolchain configuration"
    else
        echo "Error: Toolchain configuration not found: ${compiler}"
        return 1
    fi
}

# Set up Python development environment
setup_python_env() {
    local venv_dir="${DEV_BASE}/environments/python"
    if ! command -v python3 >/dev/null 2>&1; then
        echo "Python 3 not found. Please install python3 package."
        return 1
    fi

    python3 -m venv "$venv_dir"
    . "${venv_dir}/bin/activate"

    # Install essential Python development tools
    pip install --upgrade pip
    pip install pylint black mypy pytest coverage
}

# Set up Ruby development environment
setup_ruby_env() {
    if ! command -v gem >/dev/null 2>&1; then
        echo "Ruby not found. Please install ruby package."
        return 1
    fi

    # Install essential Ruby development tools
    gem install bundler rubocop rspec
}

# Configure Git
setup_git() {
    git config --global core.editor "nvim"
    git config --global color.ui auto
    git config --global pull.rebase true
    git config --global init.defaultBranch main
}

# Development utilities
create_project() {
    local name="$1"
    local type="$2"
    local dir="${DEV_BASE}/projects/${name}"

    mkdir -p "$dir"
    cd "$dir" || exit 1

    case "$type" in
        cpp)
            cp "${DEV_BASE}/samples/cpp/CMakeLists.txt" .
            mkdir -p src include test
            ;;
        python)
            cp "${DEV_BASE}/samples/python/setup.py" .
            mkdir -p src tests docs
            setup_python_env
            ;;
        *)
            echo "Unknown project type: ${type}"
            return 1
            ;;
    esac

    git init
    echo "Created ${type} project: ${name}"
}

# Execute the specified command
case "$1" in
    gcc|clang)
        load_toolchain "$1"
        ;;
    python)
        setup_python_env
        ;;
    ruby)
        setup_ruby_env
        ;;
    git)
        setup_git
        ;;
    project)
        create_project "$2" "$3"
        ;;
    *)
        echo "Usage: $0 {gcc|clang|python|ruby|git|project}"
        exit 1
        ;;
esac
EOF
    chmod 755 "${DEV_BASE}/scripts/dev-env.sh"

    # Create project templates
    mkdir -p "${DEV_BASE}/samples/cpp"
    cat > "${DEV_BASE}/samples/cpp/CMakeLists.txt" << 'EOF'
cmake_minimum_required(VERSION 3.10)
project(project_name VERSION 1.0)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Enable testing
enable_testing()

# Find packages
find_package(GTest REQUIRED)

# Add subdirectories
add_subdirectory(src)
add_subdirectory(test)

# Installation rules
install(TARGETS ${PROJECT_NAME}
        RUNTIME DESTINATION bin
        LIBRARY DESTINATION lib
        ARCHIVE DESTINATION lib/static)
EOF

    mkdir -p "${DEV_BASE}/samples/python"
    cat > "${DEV_BASE}/samples/python/setup.py" << 'EOF'
from setuptools import setup, find_packages

setup(
    name="project_name",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[],
    extras_require={
        "dev": [
            "pytest",
            "pytest-cov",
            "black",
            "mypy",
            "pylint",
        ],
    },
    python_requires=">=3.7",
)
EOF

    # Configure ccache
    mkdir -p "/home/${USERNAME}/.ccache"
    cat > "/home/${USERNAME}/.ccache/ccache.conf" << 'EOF'
max_size = 10G
compression = true
compression_level = 6
hash_dir = false
EOF

    # Add development environment settings to shell configuration
    cat >> "/home/${USERNAME}/.zshrc" << EOF
# Development Environment Configuration
export DEV_BASE="${DEV_BASE}"
export PATH="\${DEV_BASE}/scripts:\${PATH}"
export CCACHE_DIR="/home/${USERNAME}/.ccache"
export CCACHE_COMPRESS=1

# Development Aliases
alias dev='${DEV_BASE}/scripts/dev-env.sh'
alias gcc-env='dev gcc'
alias clang-env='dev clang'
alias py-env='dev python'
alias create-project='dev project'

# Build System Aliases
alias cmake='cmake -DCMAKE_EXPORT_COMPILE_COMMANDS=ON'
alias make='make -j\$(sysctl -n hw.ncpu)'
alias ninja='ninja -j\$(sysctl -n hw.ncpu)'

# Code Navigation
alias tags='ctags -R .'
alias cscope-gen='find . -name "*.c" -o -name "*.cpp" -o -name "*.h" -o -name "*.hpp" > cscope.files && cscope -b'
EOF

    # Set up ctags configuration
    cat > "/home/${USERNAME}/.ctags" << 'EOF'
--recurse=yes
--exclude=.git
--exclude=vendor/*
--exclude=node_modules/*
--exclude=db/*
--exclude=log/*
--exclude=\*.min.\*
--exclude=\*.swp
--exclude=\*.bak
--exclude=\*.pyc
--exclude=\*.class
--exclude=\*.cache
EOF

    # Set up cscope configuration
    cat > "/home/${USERNAME}/.cscoperc" << 'EOF'
-R
-b
-q
-k
EOF

    # Configure editor backup and swap directories
    mkdir -p "/home/${USERNAME}/.backup"/{undo,swap,backup}
    chmod 700 "/home/${USERNAME}/.backup"/{undo,swap,backup}

    # Set up Git global configuration
    if command -v git >/dev/null 2>&1; then
        git config --global core.editor "nvim"
        git config --global core.excludesfile "/home/${USERNAME}/.gitignore"
        git config --global init.defaultBranch "main"
        git config --global pull.rebase true
        git config --global color.ui auto
        git config --global help.autocorrect 1
    fi

    # Create global gitignore
    cat > "/home/${USERNAME}/.gitignore" << 'EOF'
# Editor files
*.swp
*.swo
*~
.*.un~
.vscode/
.idea/

# Build directories
build/
dist/
*.o
*.so
*.dylib
*.a
*.exe

# Python
__pycache__/
*.py[cod]
*.egg
*.egg-info/
.env/
.venv/
env/
venv/

# Node.js
node_modules/
npm-debug.log
yarn-debug.log
yarn-error.log

# macOS
.DS_Store
.AppleDouble
.LSOverride

# Tags and databases
tags
TAGS
.tags
.TAGS
cscope.out
cscope.in.out
cscope.po.out
EOF

    # Set appropriate permissions
    chown -R "${USERNAME}:wheel" "${DEV_BASE}"
    chown -R "${USERNAME}:wheel" "/home/${USERNAME}/.backup"
    chown "${USERNAME}:wheel" "/home/${USERNAME}/.gitignore"
    chown "${USERNAME}:wheel" "/home/${USERNAME}/.ctags"
    chown "${USERNAME}:wheel" "/home/${USERNAME}/.cscoperc"
    chown -R "${USERNAME}:wheel" "/home/${USERNAME}/.ccache"

    log_info "Development environment setup completed"
    log_info "Run 'source ~/.zshrc' to load new development environment settings"
    log_info "Use 'dev help' to see available development commands"
}

setup_oh_my_zsh() {
    # Define variables
    OMZ_DIR="${HOME}/.oh-my-zsh"
    ZSHRC_FILE="${HOME}/.zshrc"
    ZSHRC_BACKUP="${HOME}/.zshrc.pre-oh-my-zsh.$(date +%s)"
    
    # Check if Oh My Zsh is already installed
    if [ -d "${OMZ_DIR}" ]; then
        printf "Oh My Zsh is already installed at %s\n" "${OMZ_DIR}"
    else
        # Clone the Oh My Zsh repository
        printf "Cloning Oh My Zsh into %s...\n" "${OMZ_DIR}"
        if command -v git >/dev/null 2>&1; then
            git clone https://github.com/ohmyzsh/ohmyzsh.git "${OMZ_DIR}" || {
                printf "ERROR: Failed to clone Oh My Zsh repository.\n" >&2
                return 1
            }
        else
            printf "ERROR: git is not installed.\n" >&2
            return 1
        fi
    fi

    # Backup existing .zshrc if it exists and is not linked to oh-my-zsh
    if [ -f "${ZSHRC_FILE}" ] && ! grep -q "oh-my-zsh" "${ZSHRC_FILE}"; then
        printf "Backing up existing .zshrc to %s\n" "${ZSHRC_BACKUP}"
        mv "${ZSHRC_FILE}" "${ZSHRC_BACKUP}" || {
            printf "ERROR: Failed to backup existing .zshrc\n" >&2
            return 1
        }
    fi

    # Copy the Oh My Zsh template configuration if no .zshrc exists
    if [ ! -f "${ZSHRC_FILE}" ]; then
        printf "Setting up default .zshrc from Oh My Zsh template...\n"
        cp "${OMZ_DIR}/templates/zshrc.zsh-template" "${ZSHRC_FILE}" || {
            printf "ERROR: Failed to copy Oh My Zsh template .zshrc\n" >&2
            return 1
        }
        # Set ZSH environment variable in .zshrc
        sed -i '' "s|^export ZSH=.*|export ZSH=\"${OMZ_DIR}\"|" "${ZSHRC_FILE}"
    else
        printf ".zshrc already exists. Please merge changes manually if needed.\n"
    fi

    # Optionally, set Zsh as the default shell for the current user
    if [ "$(getent passwd "$(id -un)" | cut -d: -f7)" != "$(command -v zsh)" ]; then
        printf "Changing default shell to Zsh for user %s...\n" "$(id -un)"
        chsh -s "$(command -v zsh)" || {
            printf "WARNING: Failed to change default shell. You may need to do this manually.\n"
        }
    fi

    printf "Oh My Zsh setup is complete! Start a new terminal session or run 'zsh' to begin using it.\n"
}

# -----------------------------------------------------------------------------
# Main Execution
# -----------------------------------------------------------------------------
main() {
    log_info "Starting enhanced NetBSD system configuration..."

    if [ "$(id -u)" -ne 0 ]; then
        log_error "This script must be run as root"
        exit 1
    fi

    # Create log file with secure permissions
    install -m 600 /dev/null "$LOG_FILE"

    # Execute configuration functions
    install_packages
    configure_ssh
    setup_development
    # Removed configure_security as it's not defined
    setup_neovim
    configure_nginx
    configure_system_performance
    setup_backup_system
    optimize_network
    configure_kernel_development
    monitor_system_health
    configure_comprehensive_security
    configure_container_environment
    configure_testing_environment
    create_all_directories
    setup_zsh
    setup_oh_my_zsh

    log_info "Enhanced system configuration complete."
    log_info "Please review logs at $LOG_FILE for any warnings or errors."
    log_info "Remember to run 'sync' before rebooting"
}

# Execute main function
main "$@"