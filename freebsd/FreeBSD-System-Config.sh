#!/bin/zsh
# =============================================================================
# FreeBSD Advanced System Configuration and Development Environment Setup
# =============================================================================
#
# Purpose:
#   This script performs a comprehensive, automated configuration of a fresh
#   FreeBSD installation, transforming it into a fully-featured development
#   environment with enhanced security, performance optimization, and monitoring
#   capabilities. It implements best practices for system hardening while
#   maintaining usability for development work.
#
# Version: 2.0
# Author: dunamismax with Claude 3.5 Sonnet (Pro)
# Created: 2024-01-20
# License: MIT
#
# =============================================================================
# Prerequisites and System Requirements
# =============================================================================
#
# Operating System:
#   - FreeBSD 13.0 or later
#   - Clean installation recommended
#   - Root access required
#
# Minimum Hardware:
#   - CPU: 2 cores recommended
#   - RAM: 4GB minimum, 8GB recommended
#   - Storage: 20GB free space
#   - Network: Active internet connection required
#
# Required Base Packages:
#   - zsh (Shell environment)
#   - git (Version control and package management)
#   - curl (Download utilities)
#   - sudo (Privilege management)
#
# =============================================================================
# Features and Capabilities
# =============================================================================
#
# Development Environment:
#   - Neovim configuration with LSP support
#   - ZSH shell with Oh My Zsh framework
#   - Multiple language support (Python, Go, Rust, Node.js)
#   - Container development environment
#   - Advanced debugging tools
#   - Version control integration
#
# Security Enhancements:
#   - Comprehensive system hardening
#   - Enhanced SSH configuration
#   - Network security optimization
#   - File system security policies
#   - Intrusion detection setup
#   - Security monitoring and alerting
#
# Performance Optimization:
#   - Kernel parameter tuning
#   - Network stack optimization
#   - File system optimization
#   - Service performance tuning
#   - Resource management configuration
#
# System Monitoring:
#   - Health check system
#   - Performance monitoring
#   - Log management
#   - Alert configuration
#   - Resource usage tracking
#   - System analytics
#
# Backup and Recovery:
#   - Automated backup configuration
#   - Incremental backup support
#   - Remote backup capability
#   - Disaster recovery preparation
#   - Version control for configurations
#
# Network Configuration:
#   - Advanced network tuning
#   - Firewall configuration
#   - Service optimization
#   - Protocol optimization
#   - Traffic management
#
# =============================================================================
# Usage and Execution
# =============================================================================
#
# Basic Usage:
#   ./configure_system.sh [username]
#
# Required Environment Variables:
#   USERNAME    - Target user for development environment setup
#   LOG_FILE    - Location for script logging (defaults to /var/log/setup.log)
#
# Example:
#   USERNAME=developer LOG_FILE=/var/log/setup.log ./configure_system.sh
#
# =============================================================================
# Directory Structure
# =============================================================================
#
# The script creates and manages the following directory structure:
#
# /usr/local/
#   ├── container-env/    # Container environment
#   ├── test-env/        # Testing environment
#   └── tools/           # Development tools
#
# /home/[username]/
#   ├── development/     # Development workspace
#   ├── .config/         # Configuration files
#   └── .local/         # User-specific binaries
#
# =============================================================================
# Error Handling and Logging
# =============================================================================
#
# The script implements comprehensive error handling:
#   - Detailed logging of all operations
#   - Error trapping and recovery procedures
#   - Backup creation before significant changes
#   - Rollback capabilities for critical operations
#
# Log files are created in the following locations:
#   - Main log: /var/log/setup.log
#   - Error log: /var/log/system-errors/errors.log
#   - Backup log: /var/backups/setup/
#
# =============================================================================
# Customization and Configuration
# =============================================================================
#
# Configuration files are located in:
#   - /etc/system-config/
#   - /usr/local/etc/
#   - User home directory (~/.config/)
#
# Custom configurations can be added to:
#   - /usr/local/etc/custom/
#   - ~/.config/custom/
#
# =============================================================================
# Notes and Considerations
# =============================================================================
#
# - Backup your system before running this script
# - Review all configurations before applying them
# - Some services may require restart after configuration
# - System reboot recommended after complete installation
# - Monitor system logs for any post-installation issues
#
# =============================================================================

# Exit immediately if any command exits with a non-zero status and treat unset variables as errors.
set -euo pipefail

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

# Set the preferred package mirror path for FreeBSD (example URL, adjust as needed)
PKG_PATH="http://pkg.FreeBSD.org/FreeBSD:12:amd64/latest"

# Validate the system has enough resources
check_system_resources() {
    local _min_memory=$((4 * 1024 * 1024))  # 4GB in KB
    local _available_memory=$(sysctl -n hw.usermem | awk '{print $1/1024}')

    if [ "$_available_memory" -lt "$_min_memory" ]; then
        log_error "Insufficient memory available. Required: 4GB, Available: $((_available_memory/1024/1024))GB"
        return 1
    fi
}

# Validate network connectivity
verify_network_connectivity() {
    local _timeout=5
    if ! ping -c 1 -W $_timeout 8.8.8.8 >/dev/null 2>&1; then
        log_error "No network connectivity detected"
        return 1
    fi
}

# -----------------------------------------------------------------------------
# Advanced Error Handling and Logging System for FreeBSD
# Designed for production use with comprehensive error capture and analysis
# -----------------------------------------------------------------------------

# Default paths for logs and diagnostic information
: "${ERROR_LOG_DIR:=/var/log/system-errors}"
: "${ERROR_LOG:=${ERROR_LOG_DIR}/errors.log}"
: "${DIAGNOSTIC_DIR:=${ERROR_LOG_DIR}/diagnostics}"
: "${STATE_DIR:=${ERROR_LOG_DIR}/states}"
: "${LOG_FILE:=/var/log/setup.log}"

# Constants for configuration
: "${ERROR_LOG_MAX_SIZE:=$((10 * 1024 * 1024))}"  # 10MB
: "${ERROR_LOG_ROTATE_COUNT:=5}"
: "${STACK_TRACE_DEPTH:=10}"
: "${CONTEXT_LINES:=7}"

# Log levels with proper numerical values
declare -A LOG_LEVELS=(
    [TRACE]=0
    [DEBUG]=10
    [INFO]=20
    [WARN]=30
    [ERROR]=40
    [FATAL]=50
)

# Initialize the error handling subsystem with proper directory structure
init_error_handling() {
    local _dirs=("$ERROR_LOG_DIR" "$DIAGNOSTIC_DIR" "$STATE_DIR")
    local _dir

    for _dir in "${_dirs[@]}"; do
        if ! mkdir -p "$_dir" 2>/dev/null; then
            printf "CRITICAL: Failed to create directory: %s\n" "$_dir" >&2
            exit 1
        fi
        chmod 750 "$_dir"  # Secure permissions
    fi

    # Initialize error log with correct permissions
    if ! touch "$ERROR_LOG" 2>/dev/null; then
        printf "CRITICAL: Failed to create error log: %s\n" "$ERROR_LOG" >&2
        exit 1
    fi
    chmod 640 "$ERROR_LOG"  # Secure but readable by admin group

    # Create diagnostic links for quick access
    ln -sf "$ERROR_LOG" "${DIAGNOSTIC_DIR}/current_errors"
}

# Enhanced error log rotation with compression and retention
rotate_error_log() {
    local _size _timestamp _old_logs _compress_cmd

    if [ ! -f "$ERROR_LOG" ]; then
        return 0
    fi

    _size=$(stat -f %z "$ERROR_LOG" 2>/dev/null || echo 0)

    if [ "$_size" -gt "$ERROR_LOG_MAX_SIZE" ]; then
        _timestamp=$(date +%Y%m%d_%H%M%S)

        # Determine compression command availability
        if command -v zstd >/dev/null 2>&1; then
            _compress_cmd="zstd -q -19"  # Best compression
        elif command -v xz >/dev/null 2>&1; then
            _compress_cmd="xz -9"
        else
            _compress_cmd="gzip -9"
        fi

        # Rotate with compression
        mv "$ERROR_LOG" "${ERROR_LOG}.${_timestamp}"
        touch "$ERROR_LOG"
        chmod 640 "$ERROR_LOG"

        # Compress previous log in background
        ("$_compress_cmd" "${ERROR_LOG}.${_timestamp}" &)

        # Clean old logs maintaining retention policy
        _old_logs=$(find "$ERROR_LOG_DIR" -name "errors.log.*" -type f | sort -r)
        echo "$_old_logs" | tail -n "+$((ERROR_LOG_ROTATE_COUNT + 1))" | xargs rm -f 2>/dev/null
    fi
}

# -----------------------------------------------------------------------------
# Backup Management Configuration
# -----------------------------------------------------------------------------
: "${BACKUP_ROOT:=/var/backups}"
: "${BACKUP_RETENTION:=5}"        # Number of backups to retain
: "${BACKUP_PREFIX:=system-cfg}"  # Prefix for backup files

# Comprehensive backup rotation with validation and logging
rotate_backups() {
    local _backup_dir="$1"
    local _max_backups="${2:-$BACKUP_RETENTION}"
    local _prefix="${3:-$BACKUP_PREFIX}"

    # Validate input parameters
    if [ ! -d "$_backup_dir" ]; then
        log_error "Backup directory does not exist: $_backup_dir"
        return 1
    }

    # Create a secure temporary file for backup listing
    local _temp_list
    _temp_list=$(mktemp -t backup-list.XXXXXX) || {
        log_error "Failed to create temporary file for backup rotation"
        return 1
    }

    # Ensure temporary file cleanup
    trap 'rm -f "$_temp_list"' EXIT

    # List only files matching our backup prefix pattern
    find "$_backup_dir" -type f -name "${_prefix}*" -print0 | \
        xargs -0 ls -t > "$_temp_list"

    # Calculate number of backups to remove
    local _total_backups=$(wc -l < "$_temp_list")
    if [ "$_total_backups" -gt "$_max_backups" ]; then
        local _remove_count=$((_total_backups - _max_backups))
        
        # Log the rotation action
        log_info "Rotating backups in $_backup_dir: removing $_remove_count old backup(s)"
        
        # Remove old backups while keeping the most recent ones
        tail -n "$_remove_count" "$_temp_list" | while read -r backup; do
            if [ -f "$backup" ]; then
                log_debug "Removing old backup: $backup"
                rm -f "$backup" || log_warn "Failed to remove backup: $backup"
            fi
        done
    fi
}

# Comprehensive system state capture
capture_system_state() {
    local _error_id="$1"
    local _state_file="${STATE_DIR}/state_${_error_id}.log"
    local _emergency="$2"

    {
        echo "=== System State Snapshot ==="
        echo "Error ID: $_error_id"
        echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
        echo "Emergency Mode: ${_emergency:-false}"
        echo "----------------------------------------"

        # System identification
        echo "\n=== System Information ==="
        uname -a
        sysctl -a hw kern

        # Resource utilization
        echo "\n=== Resource Status ==="
        top -b -n 1
        vmstat -z
        swapinfo

        # Process and thread information
        echo "\n=== Process Status ==="
        ps auxwww
        procstat -a

        # File system status
        echo "\n=== Filesystem Status ==="
        df -hi
        mount
        fstat

        # Network status
        echo "\n=== Network Status ==="
        netstat -an
        sockstat -4l

        # Recent system messages
        echo "\n=== System Messages ==="
        tail -n 50 /var/log/messages

        # Security information
        echo "\n=== Security Status ==="
        w
        last -n 20

        if [ "${_emergency:-false}" = "true" ]; then
            # Additional emergency diagnostics
            echo "\n=== Emergency Diagnostics ==="
            dmesg
            kldstat
            sysctl kern.proc.pid
            dtrace -l 2>/dev/null
        fi

    } > "$_state_file"

    # Create quick access symlink to latest state
    ln -sf "$_state_file" "${DIAGNOSTIC_DIR}/latest_state"
}

# Advanced stack trace generation with source context
generate_stack_trace() {
    local _pid="$$"
    local _error_id="$1"
    local _line_no="$2"
    local _cmd="$3"
    local _exit_code="${4:-Unknown}"
    local _trace_file="${DIAGNOSTIC_DIR}/trace_${_error_id}.log"
    local _context_start _context_end

    {
        echo "=== Stack Trace Analysis ==="
        echo "Error ID: $_error_id"
        echo "Process ID: $_pid"
        echo "Command: $_cmd"
        echo "Exit Code: $_exit_code"
        echo "Line Number: $_line_no"
        echo "Script: $0"
        echo "Working Directory: $(pwd)"
        echo "Effective User: $(id -un) ($(id -u))"
        echo "Time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
        echo "----------------------------------------"

        # Generate full stack trace
        local _frame=0
        echo "\n=== Call Stack ==="
        while caller $_frame; do
            _frame=$((_frame + 1))
            [ $_frame -gt $STACK_TRACE_DEPTH ] && break
        done 2>/dev/null | awk '{
            printf "  [Frame %d] Line %d in function %s (File: %s)\n",
                   NR, $1, $2, $3
        }'

        # Source code context
        if [ -f "$0" ]; then
            echo "\n=== Code Context ==="
            _context_start=$((_line_no - CONTEXT_LINES))
            [ $_context_start -lt 1 ] && _context_start=1
            _context_end=$((_line_no + CONTEXT_LINES))

            sed -n "${_context_start},${_context_end}p" "$0" | awk -v err_line="$_line_no" '{
                printf "%s%4d%s │ %s\n",
                       NR == err_line ? ">" : " ",
                       NR,
                       NR == err_line ? "*" : " ",
                       $0
            }'
        fi

        # Environment state
        echo "\n=== Environment State ==="
        env | sort

        # Shell options
        echo "\n=== Shell Options ==="
        set -o

    } > "$_trace_file"

    # Create quick access symlink to latest trace
    ln -sf "$_trace_file" "${DIAGNOSTIC_DIR}/latest_trace"
}

# Comprehensive error handler with recovery attempts
handle_error() {
    local _line_no="$1"
    local _cmd="$2"
    local _exit_code="$3"
    local _error_id

    _error_id=$(dd if=/dev/urandom bs=8 count=1 2>/dev/null | od -An -tx8 | tr -d ' \t\n')

    # Rotate logs if needed
    rotate_error_log

    # Log the error
    log_error "Error occurred [ID: $_error_id] in command '$_cmd' at line $_line_no (Exit Code: $_exit_code)"

    # Generate diagnostic information
    generate_stack_trace "$_error_id" "$_line_no" "$_cmd" "$_exit_code"

    # Capture system state
    local _emergency=false

    # Check for critical system conditions
    local _mem_free _disk_free
    _mem_free=$(vmstat | awk 'NR==3{print $4}')
    _disk_free=$(df -k / | awk 'NR==2{print $4}')

    if [ "$_mem_free" -lt 1024 ] || [ "$_disk_free" -lt 102400 ]; then
        _emergency=true
        log_error "CRITICAL: System resources critically low!"
    fi

    capture_system_state "$_error_id" "$_emergency"

    # Attempt recovery based on the type of error
    case "$_cmd" in
        *pkg*install*)
            log_warn "Package installation failed, attempting cleanup..."
            pkg clean -a >/dev/null 2>&1
            pkg audit -F >/dev/null 2>&1
            ;;
        *mount*)
            log_warn "Mount operation failed, checking filesystem..."
            local _device="${_cmd##* }"
            fsck -y "$_device" >/dev/null 2>&1
            ;;
        *rm*|*mv*|*cp*)
            log_warn "File operation failed, verifying permissions..."
            local _path="${_cmd##* }"
            if [ -e "$_path" ]; then
                chown root:wheel "$_path" 2>/dev/null
                chmod 644 "$_path" 2>/dev/null
            fi
            ;;
    esac

    # Send notification if mail is available
    if [ -x /usr/bin/mail ]; then
        {
            echo "System Configuration Error Report"
            echo "================================"
            echo "Error ID: $_error_id"
            echo "Hostname: $(hostname)"
            echo "Time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
            echo "Command: $_cmd"
            echo "Line: $_line_no"
            echo "Exit Code: $_exit_code"
            echo
            echo "Detailed logs and diagnostics:"
            echo "- Error Log: $ERROR_LOG"
            echo "- Stack Trace: ${DIAGNOSTIC_DIR}/trace_${_error_id}.log"
            echo "- System State: ${STATE_DIR}/state_${_error_id}.log"
            if [ "$_emergency" = "true" ]; then
                echo
                echo "CRITICAL: System is in emergency state!"
                echo "Immediate attention required!"
            fi
        } | mail -s "[ERROR] System Configuration Failure on $(hostname)" root
    fi

    # Exit with original error code or 1
    exit "${_exit_code:-1}"
}

# Set up error trap
trap 'handle_error ${LINENO} "$BASH_COMMAND" "$?"' ERR

# Initialize error handling system
init_error_handling

# -----------------------------------------------------------------------------
# Advanced Logging System for FreeBSD
# Provides comprehensive logging with rotation, compression, and error tracking
# -----------------------------------------------------------------------------

# Default paths and thresholds for logging
: "${LOG_DIR:=/var/log/system-setup}"
: "${LOG_FILE:=${LOG_DIR}/system.log}"
: "${LOG_MAX_SIZE:=$((10 * 1024 * 1024))}"  # 10MB
: "${LOG_ROTATION_COUNT:=5}"
: "${LOG_COMPRESS_AGE:=7}"  # Days before compressing

# Log levels with proper numerical values
declare -A LOG_LEVELS=(
    [TRACE]=0
    [DEBUG]=10
    [INFO]=20
    [WARN]=30
    [ERROR]=40
    [FATAL]=50
)

# Initialize logging system
init_logging() {
    # Create log directory with secure permissions
    if ! mkdir -p "$LOG_DIR" 2>/dev/null; then
        echo "Failed to create log directory: $LOG_DIR" >&2
        return 1
    }
    chmod 750 "$LOG_DIR"

    # Initialize main log file if it doesn't exist
    if ! touch "$LOG_FILE" 2>/dev/null; then
        echo "Failed to create log file: $LOG_FILE" >&2
        return 1
    }
    chmod 640 "$LOG_FILE"

    # Create directory for archived logs
    mkdir -p "${LOG_DIR}/archive"
    chmod 750 "${LOG_DIR}/archive"

    return 0
}

# Enhanced log management with rotation and compression
manage_logs() {
    local _current_size
    
    # Check if log file exists
    if [ ! -f "$LOG_FILE" ]; then
        return 0
    }

    # Get current log size
    _current_size=$(stat -f %z "$LOG_FILE")

    # Rotate if size exceeds threshold
    if [ "$_current_size" -gt "$LOG_MAX_SIZE" ]; then
        local _timestamp=$(date +%Y%m%d_%H%M%S)
        local _rotated_log="${LOG_FILE}.${_timestamp}"
        
        # Rotate the current log file
        if mv "$LOG_FILE" "$_rotated_log"; then
            # Create new log file with correct permissions
            touch "$LOG_FILE"
            chmod 640 "$LOG_FILE"
            
            # Compress the rotated log in background
            (gzip "$_rotated_log" && 
             mv "${_rotated_log}.gz" "${LOG_DIR}/archive/" &)
        else
            echo "Failed to rotate log file: $LOG_FILE" >&2
            return 1
        fi

        # Clean up old archived logs
        find "${LOG_DIR}/archive" -name "*.gz" -mtime "+${LOG_ROTATION_COUNT}" -delete
    fi

    return 0
}

# Enhanced logging function with automatic rotation
log() {
    local _level="$1"
    shift
    local _level_num="${LOG_LEVELS[$_level]:-${LOG_LEVELS[INFO]}}"
    local _min_level_num="${LOG_LEVELS[${MIN_LOG_LEVEL:-INFO}]}"

    if [ "$_level_num" -ge "$_min_level_num" ]; then
        local _timestamp
        _timestamp=$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)

        # Format log entry
        local _log_entry
        printf -v _log_entry '[%s] [%s] [%s] %s\n' \
            "$_timestamp" \
            "$_level" \
            "$$" \
            "$*"

        # Write to log file and stdout
        if [ -n "${LOG_FILE:-}" ]; then
            echo "$_log_entry" | tee -a "$LOG_FILE"
            
            # Check log size and rotate if necessary
            manage_logs
        else
            echo "$_log_entry"
        fi
    fi
}

# Convenience logging functions with source information
log_trace() { log "TRACE" "(${BASH_SOURCE[1]##*/}:${BASH_LINENO[0]}) $*"; }
log_debug() { log "DEBUG" "(${BASH_SOURCE[1]##*/}:${BASH_LINENO[0]}) $*"; }
log_info()  { log "INFO"  "$*"; }
log_warn()  { log "WARN"  "$*"; }
log_error() { log "ERROR" "(${BASH_SOURCE[1]##*/}:${BASH_LINENO[0]}) $*"; }
log_fatal() { log "FATAL" "(${BASH_SOURCE[1]##*/}:${BASH_LINENO[0]}) $*"; }

# Set log level with validation
set_log_level() {
    local _level="${1^^}"
    if [ -n "${LOG_LEVELS[$_level]:-}" ]; then
        MIN_LOG_LEVEL="$_level"
        log_info "Log level set to $_level"
        return 0
    else
        log_error "Invalid log level: $1"
        return 1
    fi
}

# Generate log summary report
generate_log_summary() {
    local _output_file="${LOG_DIR}/summary_$(date +%Y%m%d_%H%M%S).txt"
    
    {
        echo "Log Summary Report"
        echo "================="
        echo "Generated: $(date)"
        echo
        echo "Error Statistics (last 24 hours):"
        grep -h "\[ERROR\]" "$LOG_FILE" "${LOG_DIR}/archive/"*.gz | \
            sort | uniq -c | sort -nr
        
        echo
        echo "Warning Statistics (last 24 hours):"
        grep -h "\[WARN\]" "$LOG_FILE" "${LOG_DIR}/archive/"*.gz | \
            sort | uniq -c | sort -nr
        
        echo
        echo "Log Size Statistics:"
        du -h "$LOG_FILE" "${LOG_DIR}/archive/"*.gz 2>/dev/null | \
            sort -hr
    } > "$_output_file"

    log_info "Log summary generated: $_output_file"
}

# Initialize logging system when the script starts
if ! init_logging; then
    echo "Failed to initialize logging system" >&2
    exit 1
fi
}

# -----------------------------------------------------------------------------
# Service State Verification System
# Provides comprehensive service monitoring and state validation
# -----------------------------------------------------------------------------

verify_service_state() {
    local _service="$1"
    local _port="$2"
    local _timeout="${3:-30}"  # Maximum seconds to wait for service
    local _start_time=$(date +%s)
    
    # Check if service is running
    while true; do
        if service "$_service" status >/dev/null 2>&1; then
            break
        fi
        
        # Check timeout
        if [ $(($(date +%s) - _start_time)) -gt "$_timeout" ]; then
            log_error "Service $_service failed to start within $_timeout seconds"
            return 1
        fi
        
        sleep 1
    done
    
    # Verify port is listening
    if [ -n "$_port" ]; then
        _start_time=$(date +%s)
        while true; do
            if sockstat -l | grep -q ":$_port "; then
                break
            fi
            
            if [ $(($(date +%s) - _start_time)) -gt "$_timeout" ]; then
                log_error "Service $_service is not listening on port $_port after $_timeout seconds"
                return 1
            fi
            
            sleep 1
        done
    fi
    
    log_info "Service $_service successfully verified"
    return 0
}

verify_all_services() {
    local _failed=0
    local -A services=(
        [nginx]="80"
        [sshd]="22"
        [postgresql]="5432"
        [mysql]="3306"
    )

    for _service in "${!services[@]}"; do
        local _port="${services[$_service]}"
        if ! verify_service_state "$_service" "$_port"; then
            log_error "Service verification failed for $_service"
            _failed=$((_failed + 1))
        fi
    done

    return $((_failed > 0))
}

# -----------------------------------------------------------------------------
# Consolidated Package Management System for FreeBSD
# Provides robust package installation with advanced error handling and reporting
# -----------------------------------------------------------------------------

# System paths and configuration
readonly PKG_SYSTEM_PATHS=(
    REPORT_DIR="/var/log/pkg-reports"
    CACHE_DIR="/var/cache/pkg"
    DB_DIR="/var/db/pkg"
    BACKUP_DIR="/var/backups/pkg"
    STATE_DIR="/var/run/pkg"
)

# Package priorities and categories for installation ordering
readonly PKG_PRIORITIES=(
    CRITICAL=1    # System-critical packages (openssl, pkg-config, etc.)
    ESSENTIAL=2   # Core development tools (gcc, clang, etc.)
    IMPORTANT=3   # Key development libraries (boost, ncurses, etc.)
    STANDARD=4    # Common tools (vim, tmux, etc.)
    OPTIONAL=5    # Nice-to-have packages
)

# Create and initialize the package list with metadata
create_package_list() {
    local _tmp_packages
    _tmp_packages=$(mktemp -t pkg.XXXXXX) || {
    log_error "Failed to create temporary package file"
    return 1
}

    # Write package definitions with metadata using an associative format
    cat > "$_tmp_packages" << 'END_PACKAGES'
# Package Format: name priority dependencies description

# Core Development Tools
devel/git ${PKG_PRIORITIES[ESSENTIAL]} "devel/perl5 security/openssl" "Distributed version control system"
devel/git-base ${PKG_PRIORITIES[ESSENTIAL]} "devel/git" "Core git tools"
devel/git-docs ${PKG_PRIORITIES[OPTIONAL]} "devel/git" "Git documentation"
lang/gcc10 ${PKG_PRIORITIES[CRITICAL]} "devel/binutils devel/gmake" "GNU Compiler Collection 10"
lang/clang ${PKG_PRIORITIES[CRITICAL]} "devel/cmake devel/ninja" "C/C++ compiler based on LLVM"
devel/llvm ${PKG_PRIORITIES[CRITICAL]} "devel/cmake devel/ninja" "LLVM compiler infrastructure"
devel/cmake ${PKG_PRIORITIES[ESSENTIAL]} "devel/pkgconf" "Cross-platform build system"
devel/ninja-build ${PKG_PRIORITIES[ESSENTIAL]} "" "Small build system"
devel/bmake ${PKG_PRIORITIES[ESSENTIAL]} "" "NetBSD make"
devel/autoconf ${PKG_PRIORITIES[STANDARD]} "" "Generate configuration scripts"
devel/automake ${PKG_PRIORITIES[STANDARD]} "devel/autoconf" "GNU Standards-compliant Makefile generator"
devel/libtool ${PKG_PRIORITIES[STANDARD]} "" "Generic shared library support script"
devel/pkgconf ${PKG_PRIORITIES[CRITICAL]} "" "Package compiler and linker metadata toolkit"
devel/ccache ${PKG_PRIORITIES[STANDARD]} "" "Compiler cache"

# Development Libraries
devel/boost-libs ${PKG_PRIORITIES[IMPORTANT]} "devel/boost-headers" "Free portable C++ libraries"
devel/boost-headers ${PKG_PRIORITIES[IMPORTANT]} "" "Boost C++ headers"
devel/ncurses ${PKG_PRIORITIES[IMPORTANT]} "" "Terminal handling library"
devel/readline ${PKG_PRIORITIES[IMPORTANT]} "devel/ncurses" "GNU readline library"
devel/gettext ${PKG_PRIORITIES[IMPORTANT]} "" "GNU gettext library and tools"
devel/zlib ${PKG_PRIORITIES[CRITICAL]} "" "Compression library"
security/openssl ${PKG_PRIORITIES[CRITICAL]} "" "SSL/TLS toolkit"

# Development Tools
devel/gdb ${PKG_PRIORITIES[ESSENTIAL]} "" "GNU debugger"
devel/lldb ${PKG_PRIORITIES[ESSENTIAL]} "devel/llvm" "LLVM debugger"
devel/valgrind ${PKG_PRIORITIES[STANDARD]} "" "Memory debugging tools"
devel/cgdb ${PKG_PRIORITIES[OPTIONAL]} "devel/gdb ncurses" "Curses interface to GDB"

# Editors and Development Environments
editors/vim ${PKG_PRIORITIES[STANDARD]} "" "Vi IMproved"
editors/neovim ${PKG_PRIORITIES[STANDARD]} "" "Next generation vim"
devel/ctags ${PKG_PRIORITIES[STANDARD]} "" "Code indexing tool"
devel/cscope ${PKG_PRIORITIES[OPTIONAL]} "" "Source code browser"

# Shell and Terminal Tools
shells/zsh ${PKG_PRIORITIES[IMPORTANT]} "" "Z shell"
misc/tmux ${PKG_PRIORITIES[STANDARD]} "" "Terminal multiplexer"
shells/bash ${PKG_PRIORITIES[STANDARD]} "" "GNU Bourne Again Shell"
misc/screen ${PKG_PRIORITIES[OPTIONAL]} "" "Terminal multiplexer"

# Security Tools
security/gnupg ${PKG_PRIORITIES[IMPORTANT]} "" "GNU Privacy Guard"
security/aide ${PKG_PRIORITIES[STANDARD]} "" "File integrity checker"
security/sudo ${PKG_PRIORITIES[ESSENTIAL]} "" "Privilege delegation tool"
END_PACKAGES

    echo "$_tmp_packages"
}

# Process package information and generate installation order
process_package_info() {
    local _pkg_list="$1"
    local _output_file="${_pkg_list}.processed"
    local -A _priorities _dependencies _descriptions

    # Parse package information
    while IFS= read -r _line; do
        case "$_line" in
            ''|'#'*) continue ;;
        esac

        # Extract package components
        local _name _priority _deps _desc
        _name=$(echo "$_line" | awk '{print $1}')
        _priority=$(echo "$_line" | awk '{print $2}')
        _deps=$(echo "$_line" | awk -F'"' '{print $2}')
        _desc=$(echo "$_line" | awk -F'"' '{print $4}')

        # Store package information
        _priorities[$_name]=$_priority
        _dependencies[$_name]=$_deps
        _descriptions[$_name]=$_desc
    done < "$_pkg_list"

    # Sort packages by priority and dependencies
    {
        echo "# Processed Package List - $(date)"
        echo "# Format: name priority dependencies description"

        for _priority in $(seq ${PKG_PRIORITIES[CRITICAL]} ${PKG_PRIORITIES[OPTIONAL]}); do
            for _pkg in "${!_priorities[@]}"; do
                if [ "${_priorities[$_pkg]}" = "$_priority" ]; then
                    printf "%s %s \"%s\" \"%s\"\n" \
                        "$_pkg" \
                        "${_priorities[$_pkg]}" \
                        "${_dependencies[$_pkg]}" \
                        "${_descriptions[$_pkg]}"
                fi
            done
        done
    } > "$_output_file"

    echo "$_output_file"
}

# Main package installation function
install_packages() {
    log_info "Initializing package management system..."

    # Create package list and process it
    local _pkg_list _processed_list
    _pkg_list=$(create_package_list) || return 1
    _processed_list=$(process_package_info "$_pkg_list") || return 1

    # Initialize tracking
    local _total=0 _success=0 _failed=0 _skipped=0
    local _report_dir="${PKG_SYSTEM_PATHS[REPORT_DIR]}/$(date +%Y%m%d_%H%M%S)"

    mkdir -p "$_report_dir" || return 1

    # Create status tracking files
    local _success_list="${_report_dir}/success.list"
    local _failed_list="${_report_dir}/failed.list"
    local _skipped_list="${_report_dir}/skipped.list"

    touch "$_success_list" "$_failed_list" "$_skipped_list"

    # Process each package
    while IFS= read -r _line; do
        case "$_line" in
            ''|'#'*) continue ;;
        esac

        local _package _priority
        _package=$(echo "$_line" | awk '{print $1}')
        _priority=$(echo "$_line" | awk '{print $2}')

        [ -z "$_package" ] && continue

        _total=$((_total + 1))

        log_info "Processing package: $_package (Priority: $_priority)"

        # Check if already installed
        if pkg info "$_package" >/dev/null 2>&1; then
            log_info "Package $_package is already installed"
            echo "$_package" >> "$_skipped_list"
            _skipped=$((_skipped + 1))
            continue
        fi

        # Attempt installation
        if ! pkg install -y "$_package" >/dev/null 2>&1; then
            # Handle package conflicts
            if pkg info "$_package" >/dev/null 2>&1; then
                log_warn "Package conflict detected for $_package, attempting resolution"
                if pkg delete -fy "$_package" >/dev/null 2>&1 && \
                   pkg install -y "$_package" >/dev/null 2>&1; then
                    log_info "Successfully resolved conflict and installed $_package"
                    echo "$_package" >> "$_success_list"
                    _success=$((_success + 1))
                    continue
                fi
            fi

            log_error "Failed to install $_package"
            echo "$_package" >> "$_failed_list"
            _failed=$((_failed + 1))

            # Critical package failure handling
            if [ "$_priority" -eq "${PKG_PRIORITIES[CRITICAL]}" ]; then
                log_error "Critical package $_package failed to install. Aborting."
                generate_report "$_report_dir" "$_total" "$_success" "$_failed" "$_skipped"
                return 1
            fi
        else
            log_info "Successfully installed $_package"
            echo "$_package" >> "$_success_list"
            _success=$((_success + 1))
        fi
    done < "$_processed_list"

    # Generate final report
    generate_report "$_report_dir" "$_total" "$_success" "$_failed" "$_skipped"

    # Determine overall success
    if [ "$_failed" -eq 0 ]; then
        log_info "All packages installed successfully"
        return 0
    elif [ "$_success" -gt "$((_total * 90 / 100))" ]; then
        log_warn "Installation completed with minor failures"
        return 0
    else
        log_error "Too many package installation failures"
        return 1
    fi
}

# Generate installation report
generate_report() {
    local _report_dir="$1"
    local _total="$2"
    local _success="$3"
    local _failed="$4"
    local _skipped="$5"
    local _report_file="${_report_dir}/installation_report.txt"

    {
        echo "Package Installation Report"
        echo "=========================="
        echo "Generated: $(date)"
        echo "System: $(uname -a)"
        echo ""
        echo "Summary"
        echo "-------"
        echo "Total packages processed: $_total"
        echo "Successfully installed: $_success"
        echo "Already installed (skipped): $_skipped"
        echo "Failed installations: $_failed"
        echo ""

        if [ "$_failed" -gt 0 ]; then
            echo "Failed Packages"
            echo "--------------"
            cat "${_report_dir}/failed.list"
            echo ""
        fi

        if [ "$_success" -gt 0 ]; then
            echo "Newly Installed Packages"
            echo "----------------------"
            cat "${_report_dir}/success.list"
        fi
    } > "$_report_file"

    log_info "Installation report generated at $_report_file"
}

# -----------------------------------------------------------------------------
# Advanced System Configuration Functions for FreeBSD
# Provides comprehensive performance tuning and security hardening
# -----------------------------------------------------------------------------

# System-wide configuration paths
readonly SYSTEM_PATHS=(
    SYSCTL_CONF="/etc/sysctl.conf"
    SECURITY_DIR="/etc/security"
    PF_CONF="/etc/pf.conf"
    AIDE_CONF="/etc/aide.conf"
    AIDE_DB="/var/lib/aide"
    PERIODIC_DIR="/etc/periodic/security"
    TUNING_DIR="/etc/tuning"
)

# Performance tuning parameters
readonly TUNING_PARAMS=(
    MIN_TCP_BUFFER=65536          # Minimum TCP buffer size (64KB)
    MAX_TCP_BUFFER=16777216       # Maximum TCP buffer size (16MB)
    MIN_AIO_PROCS=32             # Minimum AIO processes
    MAX_AIO_PROCS=2048           # Maximum AIO processes
    VM_MIN_FREE_PAGES=4096       # Minimum free pages for VM system
)

# Configure system performance with adaptive tuning
configure_system_performance() {
    log_info "Beginning comprehensive system performance configuration..."

    # Create tuning directory if it doesn't exist
    mkdir -p "${SYSTEM_PATHS[TUNING_DIR]}" || {
        log_error "Failed to create tuning directory"
        return 1
    }

    # Gather comprehensive system information for tuning decisions
    gather_system_info() {
        local _info_file="${SYSTEM_PATHS[TUNING_DIR]}/system_info"

        {
            echo "System Information Gathered on $(date)"
            echo "--------------------------------"

            # CPU Information
            _ncpu=$(sysctl -n hw.ncpu)
            _cpu_model=$(sysctl -n hw.model)
            _machine=$(sysctl -n hw.machine)
            _machine_arch=$(sysctl -n hw.machine_arch)

            echo "CPU Configuration:"
            echo "  Cores/Threads: $_ncpu"
            echo "  Model: $_cpu_model"
            echo "  Architecture: $_machine_arch"

            # Memory Information
            _phys_mem=$(sysctl -n hw.physmem)
            _page_size=$(sysctl -n hw.pagesize)
            _mem_mb=$(( _phys_mem / 1024 / 1024 ))
            _usable_mem=$(( _mem_mb * 80 / 100 ))  # Reserve 20% for system

            echo "Memory Configuration:"
            echo "  Physical Memory: $_mem_mb MB"
            echo "  Usable Memory: $_usable_mem MB"
            echo "  Page Size: $_page_size bytes"

            # Network Information
            echo "Network Configuration:"
            ifconfig -a | grep -E '^[a-z]|inet' | sed 's/^/  /'

            # Storage Information
            echo "Storage Configuration:"
            df -h | sed 's/^/  /'

        } > "$_info_file"

        log_info "System information gathered and saved to $_info_file"
    }

    # Calculate optimal network buffer sizes based on system capabilities
    calculate_network_parameters() {
        local _net_info_file="${SYSTEM_PATHS[TUNING_DIR]}/network_params"

        # Get network interface speeds
        local _interfaces _speed _max_speed=0
        _interfaces=$(ifconfig -l)

        for _if in $_interfaces; do
            _speed=$(ifconfig $_if | awk '/media:/ {
                if ($0 ~ /1000base/) print 1000;
                else if ($0 ~ /100base/) print 100;
                else if ($0 ~ /10base/) print 10;
                else print 0
            }')
            [ "$_speed" -gt "$_max_speed" ] && _max_speed=$_speed
        done

        # Calculate optimal buffer sizes based on bandwidth-delay product
        local _rtt_ms=100  # Assumed round-trip time of 100ms
        local _bandwidth_mbps=$_max_speed
        local _bdp_bytes=$(( _bandwidth_mbps * 1024 * 1024 * _rtt_ms / 8000 ))

        # Set buffers to 2*BDP with reasonable limits
        _tcp_buffer_max=$(( _bdp_bytes * 2 ))
        [ $_tcp_buffer_max -lt ${TUNING_PARAMS[MIN_TCP_BUFFER]} ] && \
            _tcp_buffer_max=${TUNING_PARAMS[MIN_TCP_BUFFER]}
        [ $_tcp_buffer_max -gt ${TUNING_PARAMS[MAX_TCP_BUFFER]} ] && \
            _tcp_buffer_max=${TUNING_PARAMS[MAX_TCP_BUFFER]}

        _tcp_buffer_default=$(( _tcp_buffer_max / 4 ))

        {
            echo "Network Parameters Calculated on $(date)"
            echo "-----------------------------------"
            echo "Interface Speed: $_max_speed Mbps"
            echo "RTT Estimate: $_rtt_ms ms"
            echo "BDP: $_bdp_bytes bytes"
            echo "TCP Buffer Max: $_tcp_buffer_max bytes"
            echo "TCP Buffer Default: $_tcp_buffer_default bytes"
        } > "$_net_info_file"
    }

    # Calculate optimal kernel memory parameters
    calculate_kernel_parameters() {
        local _kern_info_file="${SYSTEM_PATHS[TUNING_DIR]}/kernel_params"

        # Calculate maximum file descriptors based on memory
        _max_files=$(( _usable_mem * 1024 * 1024 / 256 ))

        # Calculate process limits
        _max_procs=$(( _usable_mem / 2 ))
        [ $_max_procs -gt 32768 ] && _max_procs=32768

        # Calculate shared memory limits
        _shmmax=$(( _phys_mem / 2 ))
        _shmall=$(( _shmmax / _page_size ))

        # Calculate AIO process limits
        _aio_max=$(( _ncpu * 64 ))
        [ $_aio_max -lt ${TUNING_PARAMS[MIN_AIO_PROCS]} ] && \
            _aio_max=${TUNING_PARAMS[MIN_AIO_PROCS]}
        [ $_aio_max -gt ${TUNING_PARAMS[MAX_AIO_PROCS]} ] && \
            _aio_max=${TUNING_PARAMS[MAX_AIO_PROCS]}

        {
            echo "Kernel Parameters Calculated on $(date)"
            echo "---------------------------------"
            echo "Maximum Files: $_max_files"
            echo "Maximum Processes: $_max_procs"
            echo "Shared Memory Max: $_shmmax bytes"
            echo "Shared Memory All: $_shmall pages"
            echo "AIO Maximum: $_aio_max processes"
        } > "$_kern_info_file"
    }

    # Generate optimized sysctl configuration
    generate_sysctl_config() {
        local _tmp_config
        _tmp_config=$(mktemp) || {
            log_error "Failed to create temporary configuration file"
            return 1
        }

        trap 'rm -f "$_tmp_config"' EXIT

        cat > "$_tmp_config" << EOF
# -----------------------------------------------------------------------------
# FreeBSD System Performance Configuration
# Generated: $(date)
# System: ${_machine_arch} with ${_ncpu} CPUs and ${_mem_mb} MB RAM
# -----------------------------------------------------------------------------

# Network Performance Tuning
net.inet.tcp.recvbuf_max=${_tcp_buffer_max}
net.inet.tcp.sendbuf_max=${_tcp_buffer_max}
net.inet.tcp.recvbuf_default=${_tcp_buffer_default}
net.inet.tcp.sendbuf_default=${_tcp_buffer_default}
net.inet.tcp.rfc1323=1
net.inet.tcp.init_win=4
net.inet.tcp.mss_ifmtu=1
net.inet.tcp.sack.enable=1
net.inet.tcp.path_mtu_discovery=1
net.inet.tcp.delayed_ack=0
net.inet.tcp.keepidle=7200
net.inet.tcp.blackhole=2
net.inet.udp.blackhole=1

# Memory Management
kern.ipc.shmmax=${_shmmax}
kern.ipc.shmall=${_shmall}
kern.ipc.somaxconn=2048
kern.ipc.maxsockbuf=$(( _tcp_buffer_max * 2 ))

# File System and I/O Tuning
kern.maxfiles=${_max_files}
kern.maxproc=${_max_procs}
kern.aio.max=${_aio_max}
kern.aio.workers_max=$(( _aio_max / 4 ))
kern.racct.enable=1

# VM System Tuning
vm.anonmin=10
vm.filemin=10
vm.execmin=5
vm.defer_swapspace_pageouts=1
vm.swapencrypt.enable=1
vm.pageout_algorithm=1
vm.min_free_kbytes=$(( ${TUNING_PARAMS[VM_MIN_FREE_PAGES]} * _page_size / 1024 ))

# Process and Threading
kern.threads.max_threads_per_proc=4096
kern.sched.slice=3
kern.sched.interact=5
EOF

        echo "$_tmp_config"
    }

    # Main configuration sequence
    gather_system_info || return 1
    calculate_network_parameters || return 1
    calculate_kernel_parameters || return 1

    local _config_file
    _config_file=$(generate_sysctl_config) || return 1

    # Backup existing configuration
    if [ -f "${SYSTEM_PATHS[SYSCTL_CONF]}" ]; then
        local _backup="${SYSTEM_PATHS[SYSCTL_CONF]}.$(date +%Y%m%d_%H%M%S)"
        if ! cp "${SYSTEM_PATHS[SYSCTL_CONF]}" "$_backup"; then
            log_error "Failed to backup existing configuration"
            return 1
        fi
        log_info "Created backup of existing configuration at ${_backup}"
    fi

    # Install and apply new configuration
    if ! mv "$_config_file" "${SYSTEM_PATHS[SYSCTL_CONF]}"; then
        log_error "Failed to install new configuration"
        return 1
    fi

    if ! sysctl -f "${SYSTEM_PATHS[SYSCTL_CONF]}"; then
        log_error "Failed to apply new configuration"
        if [ -f "$_backup" ]; then
            log_warn "Attempting to restore previous configuration"
            mv "$_backup" "${SYSTEM_PATHS[SYSCTL_CONF]}"
            sysctl -f "${SYSTEM_PATHS[SYSCTL_CONF]}"
        fi
        return 1
    fi

    # Verify critical settings
    verify_critical_settings() {
        local _failed=0
        while read -r _setting _expected; do
            local _actual
            _actual=$(sysctl -n "$_setting" 2>/dev/null)
            if [ "$_actual" != "$_expected" ]; then
                log_warn "Critical setting ${_setting} not applied correctly"
                log_warn "Expected: ${_expected}, Got: ${_actual}"
                _failed=$(( _failed + 1 ))
            fi
        done << EOF
net.inet.tcp.recvbuf_max ${_tcp_buffer_max}
net.inet.tcp.sendbuf_max ${_tcp_buffer_max}
kern.maxfiles ${_max_files}
kern.maxproc ${_max_procs}
EOF
        return $_failed
    }

    if ! verify_critical_settings; then
        log_warn "Some critical settings were not applied correctly"
        log_warn "Please review ${SYSTEM_PATHS[SYSCTL_CONF]} and system logs"
    else
        log_info "All critical settings verified successfully"
    fi

    log_info "System performance configuration completed"
    log_info "Parameter calculations and settings saved in ${SYSTEM_PATHS[TUNING_DIR]}"
    return 0
}

# Configure comprehensive system security settings
configure_comprehensive_security() {
    log_info "Beginning comprehensive security configuration..."

    # Create required security directories
    for _dir in "${SYSTEM_PATHS[SECURITY_DIR]}" "${SYSTEM_PATHS[AIDE_DB]}" \
                "${SYSTEM_PATHS[PERIODIC_DIR]}"; do
        if ! mkdir -p "$_dir"; then
            log_error "Failed to create security directory: ${_dir}"
            return 1
        fi
        chmod 750 "$_dir"
    done

    # Configure security-focused sysctl parameters
    configure_security_sysctl() {
        local _tmp_config
        _tmp_config=$(mktemp) || return 1

        cat > "$_tmp_config" << 'EOF'
# Security-focused sysctl parameters
security.bsd.hardlink_check_uid=1
security.bsd.hardlink_check_gid=1
security.bsd.unprivileged_proc_debug=0
security.bsd.unprivileged_read_msgbuf=0
security.bsd.stack_guard_page=1
security.bsd.see_other_uids=0
security.bsd.see_other_gids=0
security.bsd.unprivileged_get_quota=0
kern.randompid=1
kern.sugid_coredump=0
net.inet.tcp.drop_synfin=1
net.inet.tcp.nolocaltimewait=1
EOF

        if ! sysctl -f "$_tmp_config"; then
            log_error "Failed to apply security sysctl settings"
            rm -f "$_tmp_config"
            return 1
        fi
        rm -f "$_tmp_config"
        return 0
    }

    # Will continue with additional security configurations...
    # (This is where we'd add PF firewall, AIDE setup, etc.)
}

# Detect and configure network interfaces
detect_network_interfaces() {
    log_info "Detecting network interfaces..."

    # Get all available interfaces
    local _interfaces
    _interfaces=$(ifconfig -l) || {
        log_error "Failed to list network interfaces"
        return 1
    }

    # Detect external interface
    local _ext_if
    _ext_if=$(netstat -rn | awk '$1 == "default" {print $7; exit}')
    if [ -z "$_ext_if" ]; then
        log_warn "Could not detect external interface, analyzing available interfaces"

        # Try to identify external interface through heuristics
        for _if in $_interfaces; do
            case "$_if" in
                lo*|pflog*|enc*|faith*|plip*|sl*|ppp*|tun*)
                    continue ;;
            esac

            # Check if interface has an IP and is up
                            if ifconfig "$_if" | grep -q 'inet.*UP'; then
                    # Further validate interface by checking connectivity
                    if ping -c 1 -t 1 -I "$_if" 8.8.8.8 >/dev/null 2>&1; then
                        _ext_if="$_if"
                        log_info "Selected $_if as external interface (verified connectivity)"
                        break
                    fi
                fi
            done
        fi

        # If still no external interface found, default to first "real" interface
        if [ -z "$_ext_if" ]; then
            for _if in $_interfaces; do
                case "$_if" in
                    lo*|pflog*|enc*|faith*|plip*|sl*|ppp*|tun*) continue ;;
                    *)
                        _ext_if="$_if"
                        log_warn "Defaulting to $_if as external interface (unverified)"
                        break
                        ;;
                esac
            done
        fi
    }

    # Gather detailed information about each interface
    gather_interface_info() {
        local _if="$1"
        local _info_file="${SYSTEM_PATHS[TUNING_DIR]}/interface_${_if}_info"

        {
            echo "Interface Information for $_if ($(date))"
            echo "----------------------------------------"

            # Get basic interface information
            ifconfig "$_if" | while IFS= read -r _line; do
                echo "  $_line"
            done

            # Get interface capabilities
            echo "\nCapabilities:"
            ifconfig "$_if" | grep -E 'capabilities|options' | sed 's/^/  /'

            # Get interface statistics
            echo "\nInterface Statistics:"
            netstat -I "$_if" | sed 's/^/  /'

            # Get link status and media info
            echo "\nLink Status:"
            ifconfig "$_if" | grep -E 'media|status' | sed 's/^/  /'

        } > "$_info_file"

        return 0
    }

    # Configure interface parameters based on detected capabilities
    configure_interface() {
        local _if="$1"
        local _tmp_config

        _tmp_config=$(mktemp) || return 1

        # Get interface capabilities
        local _caps
        _caps=$(ifconfig "$_if" | grep 'capabilities' || true)

        # Generate interface-specific configuration
        {
            echo "# Interface configuration for $_if"
            echo "# Generated: $(date)"

            # Basic interface parameters
            echo "ifconfig_${_if}=\"DHCP\""

            # Configure TSO if supported
            if echo "$_caps" | grep -q 'TSO'; then
                echo "# Enable TCP Segmentation Offload"
                echo "ifconfig_${_if}=\"${ifconfig_${_if}} -tso\""
            fi

            # Configure LRO if supported
            if echo "$_caps" | grep -q 'LRO'; then
                echo "# Enable Large Receive Offload"
                echo "ifconfig_${_if}=\"${ifconfig_${_if}} -lro\""
            fi

            # Configure hardware checksums if supported
            if echo "$_caps" | grep -q 'RXCSUM'; then
                echo "# Enable hardware checksum support"
                echo "ifconfig_${_if}=\"${ifconfig_${_if}} rxcsum txcsum\""
            fi

        } > "$_tmp_config"

        # Apply configuration if possible
        if [ -w /etc/rc.conf ]; then
            cat "$_tmp_config" >> /etc/rc.conf
            log_info "Added configuration for $_if to rc.conf"
        else
            log_warn "Cannot write to rc.conf, interface configuration saved to $_tmp_config"
        fi

        # Apply settings immediately if interface is up
        if ifconfig "$_if" | grep -q 'UP'; then
            while read -r _cmd; do
                case "$_cmd" in
                    '#'*|'') continue ;;
                    *)
                        eval "ifconfig $_if $_cmd" || log_warn "Failed to apply setting: $_cmd"
                        ;;
                esac
            done < "$_tmp_config"
        fi

        rm -f "$_tmp_config"
        return 0
    }

    # Process each detected interface
    local _if
    for _if in $_interfaces; do
        case "$_if" in
            lo*|pflog*|enc*|faith*|plip*|sl*|ppp*|tun*)
                log_info "Skipping special interface $_if"
                continue
                ;;
            *)
                log_info "Processing interface $_if"
                if ! gather_interface_info "$_if"; then
                    log_warn "Failed to gather information for $_if"
                    continue
                fi

                if ! configure_interface "$_if"; then
                    log_warn "Failed to configure $_if"
                    continue
                fi
                ;;
        esac
    done

    if [ -n "$_ext_if" ]; then
        echo "$_ext_if" > "${SYSTEM_PATHS[TUNING_DIR]}/external_interface"
        log_info "External interface $_ext_if documented in ${SYSTEM_PATHS[TUNING_DIR]}/external_interface"
        return 0
    else
        log_error "No usable network interface found"
        return 1
    fi
}

# ... previous code ...

# Configure comprehensive system security parameters
configure_sysctl_security() {
    log_info "Configuring system security parameters..."

    # Calculate system-specific security parameters
    calculate_security_params() {
        # Get system memory information
        local _phys_mem _page_size _usable_mem
        _phys_mem=$(sysctl -n hw.physmem)
        _page_size=$(sysctl -n hw.pagesize)
        _usable_mem=$(( _phys_mem * 80 / 100 ))  # Reserve 20% for system

        # Calculate process limits based on memory
        local _max_proc_ratio=$(( _usable_mem / 1048576 / 32 ))  # 1 proc per 32MB
        [ $_max_proc_ratio -gt 1024 ] && _max_proc_ratio=1024

        # Calculate optimal shared memory limits
        local _shmmax=$(( _phys_mem / 2 ))
        local _shmall=$(( _shmmax / _page_size ))

        # Return calculated values
        echo "_max_proc_ratio=$_max_proc_ratio"
        echo "_shmmax=$_shmmax"
        echo "_shmall=$_shmall"
    }

    # Generate security-focused sysctl configuration
    generate_security_sysctl() {
        local _tmp_sysctl
        _tmp_sysctl=$(mktemp) || return 1

        # Get calculated parameters
        eval "$(calculate_security_params)"

        cat > "$_tmp_sysctl" << EOF
# -----------------------------------------------------------------------------
# FreeBSD Security Sysctl Configuration
# Generated: $(date)
# -----------------------------------------------------------------------------

# Process and Memory Security
kern.maxproc=${_max_proc_ratio}
kern.maxfiles=262144
kern.maxfilesperproc=65536
kern.randompid=1
kern.securelevel=2
kern.sugid_coredump=0
kern.coredump=0
kern.nodump_coredump=1

# User and Group Isolation
security.bsd.see_other_uids=0
security.bsd.see_other_gids=0
security.bsd.unprivileged_read_msgbuf=0
security.bsd.unprivileged_proc_debug=0
security.bsd.stack_guard_page=1
security.bsd.hardlink_check_uid=1
security.bsd.hardlink_check_gid=1

# Memory Protection
vm.pmap.pg_ps_enabled=1
vm.defer_swapspace_pageouts=1
vm.swapencrypt.enable=1
vm.overcommit=0
vm.swap_enabled=1
vm.kstack_pages=4
vm.max_map_count=262144

# Shared Memory Limits
kern.ipc.shmmax=${_shmmax}
kern.ipc.shmall=${_shmall}
kern.ipc.shm_use_phys=1

# Network Security
net.inet.tcp.blackhole=2
net.inet.udp.blackhole=1
net.inet.ip.random_id=1
net.inet.ip.redirect=0
net.inet.tcp.drop_synfin=1
net.inet.tcp.syncookies=1
net.inet.tcp.nolocaltimewait=1
net.inet.tcp.path_mtu_discovery=0
net.inet.icmp.bmcastecho=0
net.inet.icmp.maskrepl=0
net.inet.ip.forwarding=0
net.inet.ip.sourceroute=0
net.inet.ip.accept_sourceroute=0
net.inet.tcp.sendbuf_# -----------------------------------------------------------------------------
# Advanced Security Configuration System for FreeBSD
# Provides comprehensive system hardening, firewall configuration, and
# intrusion detection setup with extensive validation and monitoring
# -----------------------------------------------------------------------------

# Security configuration paths and constants
readonly SECURITY_PATHS=(
    PF_CONF="/etc/pf.conf"
    PF_RULES_DIR="/etc/pf.d"
    PF_TABLES_DIR="/etc/pf.tables"
    AIDE_CONF="/etc/aide.conf"
    AIDE_DB="/var/lib/aide"
    SECURITY_BACKUP="/var/backups/security"
)

# Security parameters and thresholds
readonly SECURITY_PARAMS=(
    MAX_SSH_CONN_RATE="3/60"       # Maximum SSH connections per minute
    MAX_SERVICE_CONN="100"         # Maximum concurrent connections per service
    SERVICE_CONN_RATE="15/5"       # Maximum new connections per 5 seconds
    STATE_TABLE_SIZE="100000"      # Maximum firewall state table entries
    BRUTEFORCE_BAN_TIME="86400"    # Ban time for brute force attempts (24 hours)
)

# Configure PF firewall with advanced security features
configure_pf() {
    log_info "Beginning PF firewall configuration..."

    # Create necessary directories
    for _dir in "${SECURITY_PATHS[PF_RULES_DIR]}" "${SECURITY_PATHS[PF_TABLES_DIR]}"; do
        mkdir -p "$_dir" || {
            log_error "Failed to create directory: $_dir"
            return 1
        }
        chmod 750 "$_dir"
    done

    # Initialize PF table files
    initialize_pf_tables() {
        local _tables=(
            "bruteforce"    # SSH brute force attempts
            "flood"         # DDoS attackers
            "scanners"      # Port scanners
            "spammers"      # Known spam sources
            "malware"       # Known malware hosts
        )

        for _table in "${_tables[@]}"; do
            touch "${SECURITY_PATHS[PF_TABLES_DIR]}/${_table}"
            chmod 600 "${SECURITY_PATHS[PF_TABLES_DIR]}/${_table}"
        done
    }

    # Generate optimized PF configuration
    generate_pf_config() {
        local _tmp_pf
        _tmp_pf=$(mktemp) || return 1

        # Detect network configuration
        detect_network_interfaces || {
            log_error "Failed to detect network interfaces"
            rm -f "$_tmp_pf"
            return 1
        }

        # Calculate optimal queue sizes based on interface speed
        local _if_speed
        _if_speed=$(get_interface_speed "$_ext_if")
        local _queue_size=$(( _if_speed * 1024 * 1024 / 8 ))  # Convert Mbps to bytes

        cat > "$_tmp_pf" << EOF
# -----------------------------------------------------------------------------
# FreeBSD PF Firewall Configuration
# Generated: $(date)
# System: $(uname -a)
# External Interface: ${_ext_if} (${_if_speed} Mbps)
# -----------------------------------------------------------------------------

# Interface and Service Definitions
ext_if = "${_ext_if}"
table <bruteforce> persist file "${SECURITY_PATHS[PF_TABLES_DIR]}/bruteforce"
table <flood> persist file "${SECURITY_PATHS[PF_TABLES_DIR]}/flood"
table <scanners> persist file "${SECURITY_PATHS[PF_TABLES_DIR]}/scanners"
table <malware> persist file "${SECURITY_PATHS[PF_TABLES_DIR]}/malware"

# Service Definitions
tcp_services = "{ ssh, http, https, smtp, submission, imaps }"
udp_services = "{ domain, ntp }"
icmp_types = "{ echoreq, unreach, timex }"

# Protected Networks
internal_net = "{ 10/8, 172.16/12, 192.168/16 }"
bogon_networks = "{ 127.0.0.0/8, 192.168.0.0/16, 172.16.0.0/12, \
                   10.0.0.0/8, 169.254.0.0/16, 192.0.2.0/24, \
                   0.0.0.0/8, 240.0.0.0/4 }"

# Optimization and State Management
set limit { states ${SECURITY_PARAMS[STATE_TABLE_SIZE]}, \
           frags 50000, \
           src-nodes 50000, \
           tables 1000000 }
set optimization aggressive
set block-policy drop
set require-order yes
set fingerprints "/etc/pf.os"
set state-policy if-bound
set debug urgent

# Queueing Configuration for DDoS Mitigation
queue root_q on \$ext_if bandwidth ${_if_speed}M max ${_if_speed}M
queue std_q parent root_q bandwidth 95M min 5M max ${_if_speed}M default
queue pri_q parent root_q bandwidth 5M min 1M max ${_if_speed}M

# Traffic Normalization
scrub in on \$ext_if all fragment reassemble \
    min-ttl 15 max-mss 1440 no-df
scrub out on \$ext_if all random-id max-mss 1440

# Default Security Policy
block in all
block out all
block quick from <bruteforce>
block quick from <flood>
block quick from <scanners>
block quick from <malware>
block quick from \$bogon_networks

# Anti-spoofing Protection
antispoof quick for \$ext_if inet

# Outbound Traffic Management
pass out quick on \$ext_if all modulate state \
    flags S/SA keep state \
    queue std_q

# Rate-limited Services
pass in on \$ext_if inet proto tcp to any port ssh \
    flags S/SA keep state \
    (max-src-conn 5, \
     max-src-conn-rate ${SECURITY_PARAMS[MAX_SSH_CONN_RATE]}, \
     overload <bruteforce> flush global) \
    queue pri_q

pass in on \$ext_if inet proto tcp to any port \$tcp_services \
    flags S/SA keep state \
    (max-src-conn ${SECURITY_PARAMS[MAX_SERVICE_CONN]}, \
     max-src-conn-rate ${SECURITY_PARAMS[SERVICE_CONN_RATE]}, \
     overload <flood> flush global) \
    queue std_q

# UDP Services
pass in on \$ext_if inet proto udp to any port \$udp_services \
    keep state \
    (max-src-states 100, \
     max-src-conn-rate 10/5, \
     overload <flood> flush global) \
    queue std_q

# ICMP Control
pass in inet proto icmp all icmp-type \$icmp_types \
    keep state \
    (max-src-conn-rate 10/10, \
     overload <flood> flush global)

# Adaptive Ban System
table <repeat_offenders> persist
pass in log (all) quick on \$ext_if proto tcp from any to any port ssh \
    flags S/SA keep state \
    (max-src-conn 3, \
     max-src-conn-rate 1/60, \
     overload <repeat_offenders> flush global)

# Logging Configuration
pass log (all, to pflog0) on \$ext_if proto tcp from <bruteforce> to any
pass log (all, to pflog0) on \$ext_if proto tcp from <flood> to any
pass log (all, to pflog0) on \$ext_if proto tcp from <scanners> to any
EOF

        echo "$_tmp_pf"
    }

    # Validate PF configuration
    validate_pf_config() {
        local _config="$1"

        # Basic syntax check
        if ! pfctl -nf "$_config"; then
            log_error "PF configuration syntax validation failed"
            return 1
        }

        # Check for required elements
        local _required_elements=(
            "ext_if"
            "table <bruteforce>"
            "table <flood>"
            "scrub in"
            "queue root_q"
        )

        for _element in "${_required_elements[@]}"; do
            if ! grep -q "$_element" "$_config"; then
                log_error "Missing required element: $_element"
                return 1
            fi
        done

        # Validate table paths
        while read -r _table_path; do
            if [ ! -f "$_table_path" ]; then
                log_error "Referenced table file does not exist: $_table_path"
                return 1
            fi
        done < <(grep -o 'file "[^"]*"' "$_config" | cut -d'"' -f2)

        return 0
    }

    # Main configuration sequence
    local _config_file
    _config_file=$(generate_pf_config) || return 1

    if ! validate_pf_config "$_config_file"; then
        rm -f "$_config_file"
        return 1
    fi

    # Backup existing configuration
    if [ -f "${SECURITY_PATHS[PF_CONF]}" ]; then
        local _backup="${SECURITY_PATHS[PF_CONF]}.$(date +%Y%m%d_%H%M%S)"
        if ! cp "${SECURITY_PATHS[PF_CONF]}" "$_backup"; then
            log_error "Failed to backup existing PF configuration"
            rm -f "$_config_file"
            return 1
        fi
        log_info "Created backup of existing PF configuration at $_backup"
    fi

    # Install new configuration
    if ! mv "$_config_file" "${SECURITY_PATHS[PF_CONF]}"; then
        log_error "Failed to install new PF configuration"
        return 1
    fi
    chmod 600 "${SECURITY_PATHS[PF_CONF]}"

    # Enable and load PF
    if ! pfctl -e; then
        log_error "Failed to enable PF"
        if [ -f "$_backup" ]; then
            log_warn "Attempting to restore previous configuration"
            mv "$_backup" "${SECURITY_PATHS[PF_CONF]}"
        fi
        return 1
    fi

    if ! pfctl -f "${SECURITY_PATHS[PF_CONF]}"; then
        log_error "Failed to load PF configuration"
        if [ -f "$_backup" ]; then
            log_warn "Attempting to restore previous configuration"
            mv "$_backup" "${SECURITY_PATHS[PF_CONF]}"
            pfctl -f "${SECURITY_PATHS[PF_CONF]}"
        fi
        return 1
    fi

    # Verify PF operation
    if ! pfctl -si | grep -q "Status: Enabled"; then
        log_error "PF is not running after configuration"
        return 1
    fi

    log_info "PF firewall configuration completed successfully"
    return 0
}

# Configure comprehensive system security parameters using sysctl
configure_sysctl_security() {
    log_info "Configuring system-wide security parameters..."

    # Calculate system-specific security parameters based on hardware
    calculate_security_params() {
        local _phys_mem _page_size _usable_mem
        _phys_mem=$(sysctl -n hw.physmem)
        _page_size=$(sysctl -n hw.pagesize)
        _usable_mem=$(( _phys_mem * 80 / 100 ))  # Reserve 20% for system operations

        # Calculate process limits based on available memory
        # We allocate one process per 32MB of RAM, with a maximum of 1024
        local _max_proc_ratio=$(( _usable_mem / 1048576 / 32 ))
        [ $_max_proc_ratio -gt 1024 ] && _max_proc_ratio=1024

        # Calculate shared memory limits - 50% of physical memory
        local _shmmax=$(( _phys_mem / 2 ))
        local _shmall=$(( _shmmax / _page_size ))

        # Calculate socket buffer limits - 25% of usable memory
        local _socket_buf_max=$(( _usable_mem / 4 ))
        [ $_socket_buf_max -gt 16777216 ] && _socket_buf_max=16777216  # Cap at 16MB

        # Return calculated parameters
        cat << EOF
_max_proc_ratio=$_max_proc_ratio
_shmmax=$_shmmax
_shmall=$_shmall
_socket_buf_max=$_socket_buf_max
EOF
    }

    # Generate security-focused sysctl configuration
    generate_security_sysctl() {
        local _tmp_sysctl
        _tmp_sysctl=$(mktemp) || return 1

        # Get calculated parameters
        eval "$(calculate_security_params)"

        cat > "$_tmp_sysctl" << EOF
# -----------------------------------------------------------------------------
# FreeBSD Security Sysctl Configuration
# Generated: $(date)
# System: $(uname -a)
# -----------------------------------------------------------------------------

# Process and Memory Security Parameters
# These settings control process creation and memory access protections
kern.maxproc=${_max_proc_ratio}
kern.maxfiles=262144
kern.maxfilesperproc=65536
kern.randompid=1
kern.securelevel=2
kern.sugid_coredump=0
kern.coredump=0
kern.nodump_coredump=1
kern.ps_strings=0
kern.elf32.aslr.enable=1
kern.elf64.aslr.enable=1

# User and Group Security Parameters
# These settings enforce strict privilege separation
security.bsd.see_other_uids=0
security.bsd.see_other_gids=0
security.bsd.unprivileged_read_msgbuf=0
security.bsd.unprivileged_proc_debug=0
security.bsd.stack_guard_page=1
security.bsd.hardlink_check_uid=1
security.bsd.hardlink_check_gid=1
security.bsd.unprivileged_get_quota=0

# Memory Protection Settings
# These parameters enhance memory security and prevent various attacks
vm.pmap.pg_ps_enabled=1
vm.defer_swapspace_pageouts=1
vm.swapencrypt.enable=1
vm.overcommit=0
vm.swap_enabled=1
vm.kstack_pages=4
vm.max_map_count=262144
vm.mmap_disable_threshold=0
vm.kmem_size_max=$(( _phys_mem / 2 ))
vm.kmem_size=$(( _phys_mem / 4 ))

# Shared Memory Security
# Configure shared memory limits and protections
kern.ipc.shmmax=${_shmmax}
kern.ipc.shmall=${_shmall}
kern.ipc.shm_use_phys=1
kern.ipc.somaxconn=4096
kern.ipc.maxsockbuf=${_socket_buf_max}
kern.ipc.nmbclusters=$(( _socket_buf_max / 2048 ))

# Network Security Hardening
# These settings protect against various network-based attacks
net.inet.tcp.blackhole=2
net.inet.udp.blackhole=1
net.inet.ip.random_id=1
net.inet.ip.redirect=0
net.inet.tcp.drop_synfin=1
net.inet.tcp.syncookies=1
net.inet.tcp.nolocaltimewait=1
net.inet.tcp.path_mtu_discovery=0
net.inet.icmp.bmcastecho=0
net.inet.icmp.maskrepl=0
net.inet.ip.forwarding=0
net.inet.ip.sourceroute=0
net.inet.ip.accept_sourceroute=0
net.inet.tcp.ecn.enable=1
net.inet.tcp.rfc3042=1
net.inet.tcp.rfc3390=1
net.inet.tcp.rexmit_slop=200
net.inet.tcp.finwait2_timeout=30
net.inet.tcp.persmax=60000
net.inet.tcp.persmin=5000

# Advanced Security Features
# Enable additional security protections where available
security.mac.enforce_policy=1
security.mac.mmap_revocation=1
security.mac.labeled_networking=1
security.mac.max_slots=4
security.jail.enforce_statfs=2
security.jail.mount_allowed=0
security.jail.socket_unixiproute_only=1
security.jail.sysvipc_allowed=0
EOF

        echo "$_tmp_sysctl"
    }

    # Validate sysctl configuration
    validate_sysctl_config() {
        local _config="$1"
        local _failed=0

        while read -r _setting _value; do
            case "$_setting" in
                ''|'#'*) continue ;;
            esac

            if ! sysctl -n "$_setting" >/dev/null 2>&1; then
                log_warn "Invalid sysctl setting: $_setting"
                _failed=$((_failed + 1))
            fi
        done < "$_config"

        return $((_failed > 0))
    }

    # Main configuration sequence
    local _config_file
    _config_file=$(generate_security_sysctl) || {
        log_error "Failed to generate sysctl security configuration"
        return 1
    }

    if ! validate_sysctl_config "$_config_file"; then
        log_error "Sysctl configuration validation failed"
        rm -f "$_config_file"
        return 1
    }

    # Backup existing configuration
    if [ -f "${SECURITY_PATHS[SYSCTL_CONF]}" ]; then
        local _backup="${SECURITY_PATHS[SYSCTL_CONF]}.$(date +%Y%m%d_%H%M%S)"
        if ! cp "${SECURITY_PATHS[SYSCTL_CONF]}" "$_backup"; then
            log_error "Failed to backup existing sysctl configuration"
            rm -f "$_config_file"
            return 1
        fi
        log_info "Created backup of existing sysctl configuration at $_backup"
    fi

    # Install and apply new configuration
    if ! mv "$_config_file" "${SECURITY_PATHS[SYSCTL_CONF]}"; then
        log_error "Failed to install new sysctl configuration"
        return 1
    fi
    chmod 644 "${SECURITY_PATHS[SYSCTL_CONF]}"

    # Apply settings with proper error handling
    if ! sysctl -f "${SECURITY_PATHS[SYSCTL_CONF]}"; then
        log_error "Failed to apply sysctl settings"
        if [ -f "$_backup" ]; then
            log_warn "Attempting to restore previous configuration"
            mv "$_backup" "${SECURITY_PATHS[SYSCTL_CONF]}"
            sysctl -f "${SECURITY_PATHS[SYSCTL_CONF]}"
        fi
        return 1
    fi

    # Verify critical security settings
    verify_critical_settings() {
        local _critical_settings=(
            "security.bsd.see_other_uids=0"
            "security.bsd.hardlink_check_uid=1"
            "kern.randompid=1"
            "net.inet.tcp.blackhole=2"
        )

        local _failed=0
        for _setting in "${_critical_settings[@]}"; do
            local _name="${_setting%=*}"
            local _expected="${_setting#*=}"
            local _actual

            _actual=$(sysctl -n "$_name" 2>/dev/null)
            if [ "$_actual" != "$_expected" ]; then
                log_warn "Critical setting $_name not applied correctly"
                log_warn "Expected: $_expected, Got: $_actual"
                _failed=$((_failed + 1))
            fi
        done

        return $((_failed == 0))
    }

    if ! verify_critical_settings; then
        log_warn "Some critical security settings were not applied correctly"
        log_warn "Manual verification recommended"
    else
        log_info "All critical security settings verified successfully"
    fi

    log_info "System security parameters configuration completed"
    return 0
}

# -----------------------------------------------------------------------------
# Advanced Security Monitoring and Backup System for FreeBSD
# Provides comprehensive security auditing, monitoring, and automated backups
# with extensive validation and alerting capabilities
# -----------------------------------------------------------------------------

# Configuration paths and constants
readonly SECURITY_PATHS=(
    PERIODIC_DIR="/etc/periodic/security"
    LOG_DIR="/var/log/security"
    BACKUP_ROOT="/var/backups"
    MONITORING_ROOT="/var/monitoring"
)

# Security monitoring parameters
readonly MONITORING_PARAMS=(
    REPORT_RETENTION=90        # Days to keep security reports
    ALERT_THRESHOLD=5          # Number of suspicious events before alerting
    CPU_THRESHOLD=80          # CPU usage threshold for alerts
    MEM_THRESHOLD=90          # Memory usage threshold for alerts
    DISK_THRESHOLD=90         # Disk usage threshold for alerts
)

# Configure comprehensive security monitoring system
configure_security_monitoring() {
    log_info "Configuring security monitoring system..."

    # Create necessary directories with secure permissions
    for _dir in "${SECURITY_PATHS[LOG_DIR]}" "${SECURITY_PATHS[MONITORING_ROOT]}"; do
        mkdir -p "$_dir" || {
            log_error "Failed to create directory: $_dir"
            return 1
        }
        chmod 750 "$_dir"
    done

    # Initialize monitoring databases
    initialize_monitoring_db() {
        local _db_dir="${SECURITY_PATHS[MONITORING_ROOT]}/db"
        mkdir -p "$_db_dir"

        # Create databases for various security aspects
        for _db in "login_attempts" "process_accounting" "network_connections" "file_changes"; do
            touch "${_db_dir}/${_db}.db"
            chmod 600 "${_db_dir}/${_db}.db"
        done

        return 0
    }

    # Generate the daily security audit script
    generate_security_script() {
        local _script="${SECURITY_PATHS[PERIODIC_DIR]}/daily.security"

        cat > "$_script" << 'EOF'
#!/bin/sh
# -----------------------------------------------------------------------------
# Comprehensive Daily Security Audit Script
# Performs extensive system security checks and generates detailed reports
# -----------------------------------------------------------------------------

# Initialize environment
set -e
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin

# Configuration
LOGDIR="/var/log/security"
DBDIR="/var/monitoring/db"
TODAY=$(date +%Y%m%d)
LOG="${LOGDIR}/audit_${TODAY}.log"
ALERT_LOG="${LOGDIR}/alerts_${TODAY}.log"

# Security check functions
check_file_integrity() {
    log_section "File Integrity Check"
    if command -v aide >/dev/null 2>&1; then
        aide --check 2>&1 || echo "AIDE check failed"
    else
        echo "AIDE not installed"
    fi
}

analyze_login_attempts() {
    log_section "Login Attempt Analysis"

    # Check authentication logs for patterns
    {
        echo "Failed Login Attempts (Last 24 Hours):"
        grep "Failed password" /var/log/auth.log |
            awk '{print $1,$2,$3,$11}' |
            sort | uniq -c | sort -rn | head -10

        echo "\nSuccessful Root Logins:"
        grep "session opened for user root" /var/log/auth.log |
            tail -5

        echo "\nUnusual Login Times (Outside 8AM-6PM):"
        grep "session opened" /var/log/auth.log |
            awk '$3 < "08:00:00" || $3 > "18:00:00"' |
            tail -5
    } >> "$LOG"
}

monitor_system_resources() {
    log_section "System Resource Analysis"

    # Check CPU usage
    local cpu_usage
    cpu_usage=$(top -b -n 1 | grep "CPU:" | awk '{print $2}' | cut -d. -f1)
    if [ "$cpu_usage" -gt "${MONITORING_PARAMS[CPU_THRESHOLD]}" ]; then
        log_alert "High CPU usage: ${cpu_usage}%"
    fi

    # Check memory usage
    local mem_usage
    mem_usage=$(vmstat 1 2 | tail -1 | awk '{print $4}')
    local mem_total
    mem_total=$(sysctl -n hw.physmem)
    local mem_percent
    mem_percent=$((100 - (mem_usage * 100 / mem_total)))
    if [ "$mem_percent" -gt "${MONITORING_PARAMS[MEM_THRESHOLD]}" ]; then
        log_alert "High memory usage: ${mem_percent}%"
    fi

    # Check disk usage
    df -h | awk '{if($5+0 > ${MONITORING_PARAMS[DISK_THRESHOLD]}) print "Disk space critical on",$6,"("$5")"}'
}

analyze_network_activity() {
    log_section "Network Activity Analysis"

    # Check for unusual network connections
    {
        echo "Current Network Connections:"
        netstat -ant | awk '$6 == "ESTABLISHED" {print $4,$5}' | sort | uniq -c

        echo "\nListening Services:"
        netstat -anl | grep LISTEN

        echo "\nUnusual Ports (Non-Standard):"
        netstat -ant | awk '$4 !~ /(22|80|443|25|53)/' | grep LISTEN
    } >> "$LOG"
}

check_system_files() {
    log_section "System File Analysis"

    # Check for modified system files
    {
        echo "Recently Modified System Files:"
        find /etc /usr/local/etc -type f -mtime -1 -ls

        echo "\nNew SUID/SGID Files:"
        find / -type f \( -perm -4000 -o -perm -2000 \) -mtime -1 -ls 2>/dev/null

        echo "\nWorld-Writable Files in System Directories:"
        find /etc /usr/local/etc -type f -perm -2 -ls
    } >> "$LOG"
}

monitor_process_activity() {
    log_section "Process Activity Analysis"

    # Check for resource-intensive processes
    {
        echo "High CPU/Memory Processes:"
        ps auxww | awk '$3 > 50.0 || $4 > 50.0'

        echo "\nProcesses Running as Root:"
        ps aux | grep ^root | grep -v "^root.*\[.*\]"

        echo "\nUnusual Process Names:"
        ps auxww | awk '$11 ~ /[[:punct:]]/' | grep -v "\["
    } >> "$LOG"
}

analyze_system_logs() {
    log_section "System Log Analysis"

    # Check various system logs for issues
    {
        echo "Authentication Failures:"
        grep -i "fail" /var/log/auth.log | tail -10

        echo "\nKernel Messages:"
        dmesg | grep -i "error\|fail\|invalid" | tail -10

        echo "\nCron Job Failures:"
        grep -i "fail\|error" /var/log/cron | tail -10
    } >> "$LOG"
}

# Main audit sequence
{
    echo "Security Audit Report - $(date)"
    echo "=============================="
    echo "Hostname: $(hostname)"
    echo "OS: $(uname -a)"
    echo "Audit Start Time: $(date)"
    echo "\n"

    check_file_integrity
    analyze_login_attempts
    monitor_system_resources
    analyze_network_activity
    check_system_files
    monitor_process_activity
    analyze_system_logs

    echo "\nAudit End Time: $(date)"
} > "$LOG"

# Process alerts and send notifications
if [ -s "$ALERT_LOG" ]; then
    if [ -x /usr/bin/mail ]; then
        {
            echo "Security Alerts for $(hostname)"
            echo "Generated: $(date)"
            echo "----------------------------------------"
            cat "$ALERT_LOG"
        } | mail -s "Security Alert - $(hostname)" root
    fi
fi

# Rotate old logs
find "$LOGDIR" -type f -mtime +${MONITORING_PARAMS[REPORT_RETENTION]} -delete
EOF

        chmod 750 "$_script"
        return 0
    }

    # Create backup configuration
    configure_backup_system() {
        log_info "Configuring backup system..."

        # Create backup directory structure
        for _type in daily weekly monthly; do
            mkdir -p "${SECURITY_PATHS[BACKUP_ROOT]}/$_type"
            chmod 700 "${SECURITY_PATHS[BACKUP_ROOT]}/$_type"
        done

        # Generate backup script
        cat > "/usr/local/sbin/security-backup" << 'EOF'
#!/bin/sh
# -----------------------------------------------------------------------------
# Comprehensive Security Backup Script
# Performs automated backups of security-critical system components
# -----------------------------------------------------------------------------

# Configuration
BACKUP_ROOT="/var/backups"
DATE=$(date +%Y%m%d)
RETENTION_DAYS=30

# Backup function with compression and encryption
create_security_backup() {
    local type="$1"
    local dest="${BACKUP_ROOT}/${type}"
    local backup_file="${dest}/security-${DATE}.tar.gz"

    # Create encrypted backup of security-critical files
    tar czf - \
        --exclude=/proc \
        --exclude=/sys \
        --exclude=/tmp \
        --exclude=/var/tmp \
        --exclude=/var/cache \
        --exclude=/var/backups \
        /etc/pf.conf \
        /etc/sysctl.conf \
        /etc/security \
        /var/log/security \
        /var/db/aide \
        | openssl enc -aes-256-cbc -salt -out "$backup_file"

    # Create backup manifest
    {
        echo "Security Backup Manifest - ${DATE}"
        echo "Backup Type: ${type}"
        echo "Created: $(date)"
        echo "System: $(uname -a)"
        echo "Hostname: $(hostname)"
        find /etc /var/log/security /var/db/aide -type f -ls
    } > "${backup_file}.manifest"

    # Rotate old backups
    find "$dest" -type f -mtime +${RETENTION_DAYS} -delete
}

# Create backups based on schedule
create_security_backup "daily"
[ "$(date +%u)" = "7" ] && create_security_backup "weekly"
[ "$(date +%d)" = "01" ] && create_security_backup "monthly"

# Verify backups
verify_backups() {
    local _failed=0

    for _type in daily weekly monthly; do
        local _latest
        _latest=$(ls -t "${BACKUP_ROOT}/${_type}/security-"*.tar.gz 2>/dev/null | head -1)

        if [ -f "$_latest" ]; then
            # Verify backup integrity
            if ! openssl enc -d -aes-256-cbc -salt -in "$_latest" | tar tz >/dev/null 2>&1; then
                echo "Backup verification failed: $_latest" >&2
                _failed=$((_failed + 1))
            fi
        fi
    done

    return $((_failed == 0))
}

# Send backup report
{
    echo "Security Backup Report - $(date)"
    echo "-----------------------------"
    echo "Backup Location: ${BACKUP_ROOT}"
    echo "\nBackup Sizes:"
    du -sh ${BACKUP_ROOT}/*

    if ! verify_backups; then
        echo "\nWARNING: Some backups failed verification"
    fi
} | mail -s "Security Backup Report - $(hostname)" root
EOF

        chmod 700 "/usr/local/sbin/security-backup"

        # Add to periodic tasks
        echo "0 2 * * * root /usr/local/sbin/security-backup" > /etc/cron.d/security-backup

        return 0
    }

    # Initialize monitoring system
    if ! initialize_monitoring_db; then
        log_error "Failed to initialize monitoring system"
        return 1
    fi

    # Generate security audit script
    if ! generate_security_script; then
        log_error "Failed to generate security audit script"
        return 1
    fi

    # Configure backup system
    if ! configure_backup_system; then
        log_error "Failed to configure backup system"
        return 1
    fi

    log_info "Security monitoring system configured successfully"
    return 0
}

# -----------------------------------------------------------------------------
# Advanced Neovim Configuration System
# Provides a modern, feature-rich development environment while maintaining
# clarity and performance. This setup includes intelligent code completion,
# syntax highlighting, and powerful search capabilities.
# -----------------------------------------------------------------------------

setup_neovim() {
    log_info "Beginning comprehensive Neovim setup..."

    # Define important paths for Neovim configuration
    readonly NVIM_PATHS=(
        CONFIG_DIR="/home/$USERNAME/.config/nvim"
        DATA_DIR="/home/$USERNAME/.local/share/nvim"
        CACHE_DIR="/home/$USERNAME/.cache/nvim"
        UNDO_DIR="/home/$USERNAME/.local/state/nvim/undo"
    )

    # Create necessary directory structure with proper permissions
    create_nvim_directories() {
        log_info "Creating Neovim directory structure..."

        # Create all required directories
        for _dir in \
            "${NVIM_PATHS[CONFIG_DIR]}"/{lua,plugin,after/plugin,after/ftplugin} \
            "${NVIM_PATHS[DATA_DIR]}" \
            "${NVIM_PATHS[CACHE_DIR]}" \
            "${NVIM_PATHS[UNDO_DIR]}"
        do
            if ! mkdir -p "$_dir"; then
                log_error "Failed to create directory: $_dir"
                return 1
            fi
            chmod 750 "$_dir"
        done

        return 0
    }

    # Install and configure the plugin manager (packer.nvim)
    setup_plugin_manager() {
        log_info "Setting up plugin manager..."

        local _packer_dir="${NVIM_PATHS[DATA_DIR]}/site/pack/packer/start/packer.nvim"

        if [ ! -d "$_packer_dir" ]; then
            if ! git clone --depth 1 https://github.com/wbthomason/packer.nvim "$_packer_dir"; then
                log_error "Failed to install packer.nvim"
                return 1
            fi
        fi

        return 0
    }

    # Generate the main Neovim configuration file
    generate_init_lua() {
        log_info "Generating Neovim configuration..."

        local _init_file="${NVIM_PATHS[CONFIG_DIR]}/init.lua"

        cat > "$_init_file" << 'EOF'
--------------------------------------------------------------------------------
-- Neovim Configuration
-- A modern development environment focused on efficiency and clarity
--------------------------------------------------------------------------------

-- Core Editor Settings
-- These settings establish a clean, efficient editing environment
local opt = vim.opt

-- Display settings for better code visibility
opt.number = true                -- Show line numbers
opt.relativenumber = true        -- Show relative line numbers for easy navigation
opt.wrap = false                -- Disable line wrapping
opt.scrolloff = 8               -- Keep 8 lines visible above/below cursor
opt.sidescrolloff = 8           -- Keep 8 columns visible left/right of cursor
opt.colorcolumn = '80'          -- Show column guide at 80 characters

-- File handling and backup settings
opt.swapfile = false            -- Disable swap files for modern systems
opt.backup = false              -- Disable backup files
opt.undofile = true             -- Enable persistent undo history
opt.undodir = vim.fn.expand('~/.local/state/nvim/undo')

-- Search and replace settings
opt.hlsearch = false            -- Don't highlight all search matches
opt.incsearch = true            -- Show search matches as you type
opt.ignorecase = true           -- Case-insensitive search...
opt.smartcase = true            -- ...unless uppercase is used

-- Visual settings for modern displays
opt.termguicolors = true        -- Enable 24-bit RGB colors
opt.signcolumn = 'yes'          -- Always show sign column
opt.cmdheight = 2               -- More space for command line
opt.showmode = false            -- Mode is shown in status line instead

-- System performance settings
opt.updatetime = 50             -- Faster completion
opt.timeoutlen = 300            -- Faster key sequence completion
opt.hidden = true               -- Enable background buffers

-- Indentation and formatting
opt.tabstop = 4                 -- Visual spaces per tab
opt.softtabstop = 4             -- Spaces per tab when editing
opt.shiftwidth = 4              -- Spaces for autoindent
opt.expandtab = true            -- Convert tabs to spaces
opt.smartindent = true          -- Smart autoindenting on new lines
opt.autoindent = true           -- Copy indent from current line

-- Plugin Management
-- Using packer.nvim for efficient plugin management
require('packer').startup(function(use)
    -- Package manager
    use 'wbthomason/packer.nvim'

    -- Syntax and language support
    use {
        'nvim-treesitter/nvim-treesitter',
        run = ':TSUpdate',
        config = function()
            require('nvim-treesitter.configs').setup({
                ensure_installed = {
                    'c', 'lua', 'vim', 'python', 'javascript',
                    'typescript', 'rust', 'go', 'bash', 'markdown'
                },
                highlight = {
                    enable = true,
                    additional_vim_regex_highlighting = false,
                },
                indent = { enable = true },
                incremental_selection = { enable = true },
            })
        end
    }

    -- Fuzzy finding and navigation
    use {
        'nvim-telescope/telescope.nvim',
        requires = {
            'nvim-lua/plenary.nvim',
            'nvim-tree/nvim-web-devicons',
            { 'nvim-telescope/telescope-fzf-native.nvim', run = 'make' }
        },
        config = function()
            require('telescope').setup({
                defaults = {
                    file_ignore_patterns = { 'node_modules', '.git' },
                    layout_strategy = 'horizontal',
                    layout_config = {
                        width = 0.95,
                        height = 0.85,
                        preview_width = 0.5,
                    },
                }
            })
        end
    }

    -- LSP Configuration
    use {
        'neovim/nvim-lspconfig',
        requires = {
            'hrsh7th/nvim-cmp',
            'hrsh7th/cmp-nvim-lsp',
            'hrsh7th/cmp-buffer',
            'hrsh7th/cmp-path',
            'L3MON4D3/LuaSnip',
            'saadparwaiz1/cmp_luasnip',
        },
        config = function()
            -- LSP server configurations
            local lspconfig = require('lspconfig')
            local capabilities = require('cmp_nvim_lsp').default_capabilities()

            -- Configure language servers
            local servers = {
                'pyright',    -- Python
                'clangd',     -- C/C++
                'tsserver',   -- TypeScript/JavaScript
                'rust_analyzer', -- Rust
                'gopls',      -- Go
            }

            for _, server in ipairs(servers) do
                lspconfig[server].setup({
                    capabilities = capabilities,
                    flags = {
                        debounce_text_changes = 150,
                    },
                })
            end

            -- Completion system configuration
            local cmp = require('cmp')
            local luasnip = require('luasnip')

            cmp.setup({
                snippet = {
                    expand = function(args)
                        luasnip.lsp_expand(args.body)
                    end,
                },
                mapping = cmp.mapping.preset.insert({
                    ['<C-Space>'] = cmp.mapping.complete(),
                    ['<CR>'] = cmp.mapping.confirm({ select = true }),
                    ['<Tab>'] = cmp.mapping(function(fallback)
                        if cmp.visible() then
                            cmp.select_next_item()
                        elseif luasnip.expand_or_jumpable() then
                            luasnip.expand_or_jump()
                        else
                            fallback()
                        end
                    end, { 'i', 's' }),
                }),
                sources = {
                    { name = 'nvim_lsp' },
                    { name = 'luasnip' },
                    { name = 'buffer' },
                    { name = 'path' },
                },
            })
        end
    }

    -- Visual theme and status line
    use {
        'sainnhe/gruvbox-material',
        config = function()
            vim.g.gruvbox_material_background = 'hard'
            vim.g.gruvbox_material_better_performance = 1
            vim.cmd('colorscheme gruvbox-material')
        end
    }

    use {
        'nvim-lualine/lualine.nvim',
        requires = { 'nvim-tree/nvim-web-devicons' },
        config = function()
            require('lualine').setup({
                options = {
                    theme = 'gruvbox-material',
                    component_separators = '|',
                    section_separators = '',
                },
                sections = {
                    lualine_a = {'mode'},
                    lualine_b = {'branch', 'diff'},
                    lualine_c = {'filename'},
                    lualine_x = {'encoding', 'fileformat', 'filetype'},
                    lualine_y = {'progress'},
                    lualine_z = {'location'}
                },
            })
        end
    }

    -- Git integration
    use {
        'lewis6991/gitsigns.nvim',
        config = function()
            require('gitsigns').setup({
                signs = {
                    add = { text = '│' },
                    change = { text = '│' },
                    delete = { text = '_' },
                    topdelete = { text = '‾' },
                    changedelete = { text = '~' },
                },
                current_line_blame = true,
            })
        end
    }
end)

-- Key Mappings
-- Establish efficient keyboard shortcuts for common operations
local keymap = vim.keymap.set
vim.g.mapleader = ' '  -- Set Space as the leader key

-- File navigation
keymap('n', '<leader>ff', require('telescope.builtin').find_files)
keymap('n', '<leader>fg', require('telescope.builtin').live_grep)
keymap('n', '<leader>fb', require('telescope.builtin').buffers)
keymap('n', '<leader>fh', require('telescope.builtin').help_tags)

-- LSP navigation
keymap('n', '<leader>e', vim.diagnostic.open_float)
keymap('n', '[d', vim.diagnostic.goto_prev)
keymap('n', ']d', vim.diagnostic.goto_next)
keymap('n', '<leader>q', vim.diagnostic.setloclist)

-- LSP key bindings for code navigation and manipulation
vim.api.nvim_create_autocmd('LspAttach', {
    group = vim.api.nvim_create_augroup('UserLspConfig', {}),
    callback = function(ev)
        local opts = { buffer = ev.buf }
        keymap('n', 'gD', vim.lsp.buf.declaration, opts)
        keymap('n', 'gd', vim.lsp.buf.definition, opts)
        keymap('n', 'K', vim.lsp.buf.hover, opts)
        keymap('n', 'gi', vim.lsp.buf.implementation, opts)
        keymap('n', '<C-k>', vim.lsp.buf.signature_help, opts)
        keymap('n', '<leader>D', vim.lsp.buf.type_definition, opts)
        keymap('n', '<leader>rn', vim.lsp.buf.rename, opts)
        keymap('n', '<leader>ca', vim.lsp.buf.code_action, opts)
        keymap('n', 'gr', vim.lsp.buf.references, opts)
    end,
})

-- Custom Functions
-- Add useful functionality for specific development tasks
local function setup_commands()
    -- Format current buffer
    vim.api.nvim_create_user_command('Format', function()
        vim.lsp.buf.format({ async = true })
    end, {})

    -- Toggle relative line numbers
    vim.api.nvim_create_user_command('ToggleNumbers', function()
        vim.wo.relativenumber = not vim.wo.relativenumber
    end, {})
end

setup_commands()
EOF

        return 0
    }

    # Create plugin installation script
    create_plugin_installer() {
        log_info "Creating plugin installation script..."

        local _install_script="/home/$USERNAME/install_nvim_plugins.sh"

        cat > "$_install_script" << 'EOF'
#!/bin/sh
# Install Neovim plugins and language servers
nvim --headless -c 'autocmd User PackerComplete quitall' -c 'PackerSync'

# Install common language servers
npm install -g pyright typescript-language-server
cargo install rust-analyzer
go install golang.org/x/tools/gopls@latest
EOF

        chmod +x "$_install_script"
        return 0
    }

    # Main setup sequence
    if ! create_nvim_directories; then
        log_error "Failed to create Neovim directories"
        return 1
    fi

    if ! setup_plugin_manager; then
        log_error "Failed to setup plugin manager"
        return 1
    fi

    if ! generate_init_lua; then
        log_error "Failed to generate Neovim configuration"
        return 1
    fi

    if ! create_plugin_installer; then
        log_error "Failed to create plugin installer"
        return 1
    fi

    # Set proper ownership
    chown -R "$USERNAME:wheel" "/home/$USERNAME/.config"
    chown -R "$USERNAME:wheel" "/home/$USERNAME/.local"
    chown -R "$USERNAME:wheel" "/home/$USERNAME/.cache"

    log_info "Neovim configuration completed successfully"
    log_info "Run ~/install_nvim_plugins.sh to complete the setup"
    return 0
}

# -----------------------------------------------------------------------------
# Advanced Network and NGINX Configuration System for FreeBSD
# Provides comprehensive network optimization and secure web server setup
# with detailed documentation and robust error handling
# -----------------------------------------------------------------------------

# Configuration paths and constants
readonly SYSTEM_PATHS=(
    NGINX_CONFIG="/etc/nginx"
    NGINX_SITES="/etc/nginx/sites-available"
    NGINX_ENABLED="/etc/nginx/sites-enabled"
    SSL_PATH="/etc/letsencrypt/live"
    ACME_PATH="/var/www/acme"
    LOG_PATH="/var/log/nginx"
)

# Network tuning parameters based on common scenarios
readonly NETWORK_PARAMS=(
    MAX_CONNECTIONS=1024        # Maximum concurrent connections
    KEEPALIVE_TIMEOUT=65       # Connection keepalive timeout in seconds
    WORKER_PROCESSES="auto"    # NGINX worker processes
    BUFFER_SIZE="512k"        # Log buffer size
    FLUSH_INTERVAL="1m"       # Log flush interval
)

# Optimize network stack for modern high-performance operations
optimize_network() {
    log_info "Beginning comprehensive network optimization..."

    # Calculate optimal network parameters based on system resources
    calculate_network_params() {
        local _mem_total
        _mem_total=$(sysctl -n hw.physmem)

        # Calculate optimal buffer sizes (25% of available memory)
        local _buffer_size=$(( _mem_total / 4 ))
        [ $_buffer_size -gt 16777216 ] && _buffer_size=16777216  # Cap at 16MB

        # Calculate maximum number of file descriptors
        local _max_files=$(( _mem_total / 1048576 ))  # Roughly 1 file per MB of RAM
        [ $_max_files -gt 262144 ] && _max_files=262144  # Cap at 256K

        cat << EOF
# Network Buffer Configuration
kern.ipc.maxsockbuf=${_buffer_size}
kern.ipc.nmbclusters=$(( _buffer_size / 2048 ))
kern.maxfiles=${_max_files}
kern.maxfilesperproc=$(( _max_files / 2 ))

# TCP Stack Optimization
net.inet.tcp.sendspace=262144
net.inet.tcp.recvspace=262144
net.inet.tcp.sendbuf_max=16777216
net.inet.tcp.recvbuf_max=16777216
net.inet.tcp.sendbuf_inc=16384
net.inet.tcp.recvbuf_inc=16384

# Modern TCP Features
net.inet.tcp.rfc1323=1         # Enable TCP window scaling
net.inet.tcp.sack.enable=1     # Enable selective acknowledgment
net.inet.tcp.path_mtu_discovery=1  # Enable MTU discovery
net.inet.tcp.blackhole=2       # Drop RST packets for closed ports
net.inet.tcp.drop_synfin=1     # Drop TCP packets with SYN+FIN
net.inet.tcp.syncache.rexmtlimit=0  # Disable retransmission limit
net.inet.tcp.msl=2000          # Reduce TIME_WAIT period

# UDP Optimization
net.inet.udp.blackhole=1       # Drop UDP packets for closed ports
net.inet.udp.maxdgram=65536    # Maximum UDP datagram size

# Network Security
net.inet.ip.random_id=1        # Randomize IP IDs
net.inet.ip.redirect=0         # Disable IP redirects
net.inet.icmp.drop_redirect=1  # Drop ICMP redirects
net.inet.icmp.bmcastecho=0     # Disable broadcast ICMP echo
net.inet.ip.stealth=1          # Enable stealth mode

# Network Queue Management
net.inet.ip.dummynet.io_fast=1
net.inet.ip.fastforwarding=1
EOF
    }

    # Generate network optimization configuration
    local _tmp_config
    _tmp_config=$(mktemp) || {
        log_error "Failed to create temporary network configuration"
        return 1
    }

    calculate_network_params > "$_tmp_config"

    # Backup existing configuration
    if [ -f "$SYSCTL_CONF" ]; then
        cp "$SYSCTL_CONF" "${SYSCTL_CONF}.$(date +%Y%m%d_%H%M%S)" || {
            log_error "Failed to backup sysctl configuration"
            rm -f "$_tmp_config"
            return 1
        }
    fi

    # Apply new configuration
    cat "$_tmp_config" >> "$SYSCTL_CONF" || {
        log_error "Failed to update sysctl configuration"
        rm -f "$_tmp_config"
        return 1
    }

    # Apply settings
    if ! sysctl -f "$SYSCTL_CONF"; then
        log_error "Failed to apply network optimizations"
        rm -f "$_tmp_config"
        return 1
    }

    rm -f "$_tmp_config"
    log_info "Network optimization completed successfully"
    return 0
}

# Configure NGINX with security hardening and performance optimization
configure_nginx() {
    log_info "Beginning comprehensive NGINX configuration..."

    # Create required directory structure
    create_nginx_directories() {
        local _dirs=(
            "${SYSTEM_PATHS[NGINX_CONFIG]}/conf.d"
            "${SYSTEM_PATHS[NGINX_SITES]}"
            "${SYSTEM_PATHS[NGINX_ENABLED]}"
            "${SYSTEM_PATHS[LOG_PATH]}"
            "${SYSTEM_PATHS[ACME_PATH]}"
        )

        for _dir in "${_dirs[@]}"; do
            if ! mkdir -p "$_dir"; then
                log_error "Failed to create directory: $_dir"
                return 1
            fi
            chmod 750 "$_dir"
        done

        return 0
    }

    # Generate main NGINX configuration
    generate_nginx_config() {
        local _main_config="${SYSTEM_PATHS[NGINX_CONFIG]}/nginx.conf"

        # Calculate worker connections based on available resources
        local _max_connections
        _max_connections=$(ulimit -n)
        [ $_max_connections -gt 65535 ] && _max_connections=65535

        cat > "$_main_config" << EOF
# -----------------------------------------------------------------------------
# NGINX Configuration
# Optimized for security and performance
# Generated: $(date)
# -----------------------------------------------------------------------------

user nginx;
worker_processes ${NETWORK_PARAMS[WORKER_PROCESSES]};
worker_rlimit_nofile $_max_connections;
pid /var/run/nginx.pid;

# Load dynamic modules
include /etc/nginx/modules/*.conf;

events {
    worker_connections $_max_connections;
    multi_accept on;
    use kqueue;
}

http {
    # Basic Settings
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout ${NETWORK_PARAMS[KEEPALIVE_TIMEOUT]};
    keepalive_requests 100;
    reset_timedout_connection on;
    client_body_timeout 10;
    send_timeout 2;

    # Buffer Size Optimization
    client_body_buffer_size 128k;
    client_max_body_size 10m;
    client_header_buffer_size 1k;
    large_client_header_buffers 4 8k;
    output_buffers 1 32k;
    postpone_output 1460;

    # Hash Table Optimization
    types_hash_max_size 2048;
    server_names_hash_bucket_size 64;
    server_names_hash_max_size 512;
    variables_hash_max_size 1024;

    # MIME Types
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    # SSL Configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers EECDH+AESGCM:EDH+AESGCM:AES256+EECDH:AES256+EDH;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    ssl_session_tickets off;
    ssl_stapling on;
    ssl_stapling_verify on;
    resolver 8.8.8.8 8.8.4.4 valid=300s;
    resolver_timeout 5s;

    # Security Headers
    add_header X-Frame-Options SAMEORIGIN;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Referrer-Policy "strict-origin-when-cross-origin";

    # Logging Configuration
    log_format main '\$remote_addr - \$remote_user [\$time_local] "\$request" '
                    '\$status \$body_bytes_sent "\$http_referer" '
                    '"\$http_user_agent" "\$http_x_forwarded_for"';

    access_log ${SYSTEM_PATHS[LOG_PATH]}/access.log main
               buffer=${NETWORK_PARAMS[BUFFER_SIZE]}
               flush=${NETWORK_PARAMS[FLUSH_INTERVAL]};
    error_log ${SYSTEM_PATHS[LOG_PATH]}/error.log warn;

    # Gzip Compression
    gzip on;
    gzip_disable "msie6";
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_buffers 16 8k;
    gzip_http_version 1.1;
    gzip_min_length 256;
    gzip_types
        application/atom+xml
        application/javascript
        application/json
        application/ld+json
        application/manifest+json
        application/rss+xml
        application/vnd.geo+json
        application/vnd.ms-fontobject
        application/x-font-ttf
        application/x-web-app-manifest+json
        application/xhtml+xml
        application/xml
        font/opentype
        image/bmp
        image/svg+xml
        image/x-icon
        text/cache-manifest
        text/css
        text/plain
        text/vcard
        text/vnd.rim.location.xloc
        text/vtt
        text/x-component
        text/x-cross-domain-policy;

    # FastCGI Optimization
    fastcgi_buffers 8 16k;
    fastcgi_buffer_size 32k;
    fastcgi_connect_timeout 60s;
    fastcgi_send_timeout 60s;
    fastcgi_read_timeout 60s;

    # Virtual Host Configs
    include /etc/nginx/conf.d/*.conf;
    include /etc/nginx/sites-enabled/*;
}
EOF

        return 0
    }

    # Generate site configurations
    generate_site_configs() {
        # Main website configuration
        cat > "${SYSTEM_PATHS[NGINX_SITES]}/dunamismax.com" << EOF
# Redirect www to non-www over HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name www.dunamismax.com dunamismax.com;

    # Redirect all HTTP traffic to HTTPS
    location / {
        return 301 https://dunamismax.com\$request_uri;
    }

    # ACME challenge handling
    location /.well-known/acme-challenge/ {
        root ${SYSTEM_PATHS[ACME_PATH]};
        try_files \$uri =404;
    }
}

# HTTPS configuration for www subdomain
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name www.dunamismax.com;

    ssl_certificate ${SYSTEM_PATHS[SSL_PATH]}/dunamismax.com/fullchain.pem;
    ssl_certificate_key ${SYSTEM_PATHS[SSL_PATH]}/dunamismax.com/privkey.pem;

    return 301 https://dunamismax.com\$request_uri;
}

# Main HTTPS server
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name dunamismax.com;

    ssl_certificate ${SYSTEM_PATHS[SSL_PATH]}/dunamismax.com/fullchain.pem;
    ssl_certificate_key ${SYSTEM_PATHS[SSL_PATH]}/dunamismax.com/privkey.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options SAMEORIGIN;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Content-Security-Policy "default-src 'self' https: data: 'unsafe-inline' 'unsafe-eval'";

    root /home/sawyer/github/hugo/dunamismax.com/public;
    index index.html;

    # Deny access to hidden files
    location ~ /\. {
        deny all;
        location ^~ /.well-known/ {
            allow all;
        }
    }

    # Static file handling
    location ~* \.(jpg|jpeg|png|gif|ico|css|js)$ {
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }

    location / {
        try_files \$uri \$uri/ =404;

        # Basic DoS protection
        limit_req zone=one burst=10 nodelay;
        limit_conn addr 10;
    }

    # Error pages
    error_page 404 /404.html;
    error_page 500 502 503 504 /50x.html;

    # Logging
    access_log ${SYSTEM_PATHS[LOG_PATH]}/dunamismax_access.log combined buffer=512k;
    error_log ${SYSTEM_PATHS[LOG_PATH]}/dunamismax_error.log warn;
}
EOF

        # Cloud subdomain configuration
        cat > "${SYSTEM_PATHS[NGINX_SITES]}/cloud.dunamismax.com" << EOF
# HTTP to HTTPS redirect
server {
    listen 80;
    listen [::]:80;
    server_name cloud.dunamismax.com;

    location / {
        return 301 https://\$server_name\$request_uri;
    }

    location /.well-known/acme-challenge/ {
        root ${SYSTEM_PATHS[ACME_PATH]};
        try_files \$uri =404;
    }
}

# HTTPS configuration
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name cloud.dunamismax.com;

    ssl_certificate ${SYSTEM_PATHS[SSL_PATH]}/cloud.dunamismax.com/fullchain.pem;
    ssl_certificate_key ${SYSTEM_PATHS[SSL_PATH]}/cloud.dunamismax.com/privkey.pem;

    # Enhanced security headers for cloud services
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Frame-Options SAMEORIGIN;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Referrer-Policy "strict-origin-when-cross-origin";
    add_header Permissions-Policy "camera=(), microphone=(), geolocation=()";
    add_header Content-Security-Policy "default-src 'self' https: data: 'unsafe-inline' 'unsafe-eval'; frame-ancestors 'self'";

    # Client body size increased for file uploads
    client_max_body_size 10G;
    client_body_timeout 300s;

    # Optimized proxy settings for cloud services
    location / {
        proxy_pass http://127.0.0.1:8080;

        # Standard proxy headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Additional headers for cloud services
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port $server_port;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Extended timeouts for large file transfers
        proxy_connect_timeout 60s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;

        # Buffering configuration
        proxy_request_buffering on;
        proxy_buffering on;
        proxy_buffer_size 128k;
        proxy_buffers 4 256k;
        proxy_busy_buffers_size 256k;

        # Optimized caching directives
        proxy_cache_use_stale error timeout http_500 http_502 http_503 http_504;
        proxy_cache_revalidate on;
        proxy_cache_min_uses 3;

        # Error handling
        proxy_intercept_errors on;
        error_page 500 502 503 504 /50x.html;
    }

    # Dedicated location for WebDAV operations
    location /.well-known/carddav {
        return 301 $scheme://$host/remote.php/dav;
    }

    location /.well-known/caldav {
        return 301 $scheme://$host/remote.php/dav;
    }

    # Deny access to sensitive locations
    location ~ ^/(?:build|tests|config|lib|3rdparty|templates|data)/ {
        deny all;
    }

    location ~ ^/(?:\.|autotest|occ|issue|indie|db_|console) {
        deny all;
    }

    # Static file handling with aggressive caching
    location ~* \.(?:css|js|woff|svg|gif|png|html|ttf|ico|jpg|jpeg|map)$ {
        try_files $uri /index.php$uri$is_args$args;
        expires 6M;
        access_log off;
        add_header Cache-Control "public, no-transform";
    }

    # Dedicated logging
    access_log ${SYSTEM_PATHS[LOG_PATH]}/cloud_access.log combined buffer=512k;
    error_log ${SYSTEM_PATHS[LOG_PATH]}/cloud_error.log warn;
}
EOF

        return 0
    }

    # Create symlinks for enabled sites
    create_site_symlinks() {
        for _site in dunamismax.com cloud.dunamismax.com; do
            if ! ln -sf "${SYSTEM_PATHS[NGINX_SITES]}/$_site" \
                      "${SYSTEM_PATHS[NGINX_ENABLED]}/$_site"; then
                log_error "Failed to create symlink for $_site"
                return 1
            fi
        done
        return 0
    }

    # Set up proper permissions
    configure_permissions() {
        # Ensure NGINX user exists
        pw user show nginx >/dev/null 2>&1 || pw useradd nginx -s /sbin/nologin

        # Set directory permissions
        chown -R nginx:nginx "${SYSTEM_PATHS[LOG_PATH]}"
        chown -R nginx:nginx "${SYSTEM_PATHS[ACME_PATH]}"
        chmod 750 "${SYSTEM_PATHS[LOG_PATH]}"
        chmod 750 "${SYSTEM_PATHS[ACME_PATH]}"

        return 0
    }

    # Update PF rules for web services
    update_pf_rules() {
        local _tmp_rules
        _tmp_rules=$(mktemp) || return 1

        cat >> "$_tmp_rules" << EOF

# Web Service Rules
table <webports> { 80, 443 }
pass in quick on \$ext_if proto tcp from any to any port <webports> flags S/SA keep state
EOF

        if ! cat "$_tmp_rules" >> /etc/pf.conf; then
            log_error "Failed to update PF rules"
            rm -f "$_tmp_rules"
            return 1
        fi

        rm -f "$_tmp_rules"
        pfctl -f /etc/pf.conf
        return 0
    }

    # Enable NGINX in rc.conf
    enable_nginx_service() {
        if ! sysrc nginx_enable="YES"; then
            log_error "Failed to enable NGINX service"
            return 1
        fi
        return 0
    }

    # Main configuration sequence
    log_info "Starting NGINX configuration sequence..."

    if ! create_nginx_directories; then
        log_error "Directory creation failed"
        return 1
    fi

    if ! generate_nginx_config; then
        log_error "NGINX configuration generation failed"
        return 1
    fi

    if ! generate_site_configs; then
        log_error "Site configuration generation failed"
        return 1
    fi

    if ! create_site_symlinks; then
        log_error "Site symlink creation failed"
        return 1
    fi

    if ! configure_permissions; then
        log_error "Permission configuration failed"
        return 1
    fi

    if ! update_pf_rules; then
        log_error "PF rules update failed"
        return 1
    fi

    if ! enable_nginx_service; then
        log_error "Service enablement failed"
        return 1
    fi

    # Start or restart NGINX
    if service nginx status >/dev/null 2>&1; then
        log_info "Restarting NGINX service..."
        service nginx restart
    else
        log_info "Starting NGINX service..."
        service nginx start
    fi

    if ! service nginx status >/dev/null 2>&1; then
        log_error "NGINX service failed to start"
        return 1
    fi

    log_info "NGINX configuration completed successfully"

    # After starting NGINX, verify its state
    if ! verify_service_state "nginx" "$_nginx_port"; then
        log_error "NGINX service failed to initialize properly"
        # Try to gather diagnostic information
        {
            echo "NGINX Error Report"
            echo "=================="
            echo "Date: $(date)"
            echo "Configuration Test Output:"
            nginx -t
            echo "Process Status:"
            ps aux | grep nginx
            echo "Port Status:"
            sockstat -l | grep nginx
            echo "Error Log Tail:"
            tail -n 50 /var/log/nginx/error.log
        } > "/var/log/nginx/startup_failure_$(date +%Y%m%d_%H%M%S).log"
        return 1
    fi
}
    return 0
}

#!/bin/zsh

configure_kernel_development() {
    local _username="$1"
    if [[ -z "$_username" ]]; then
        log_error "Username not provided for kernel development setup"
        return 1
    }

    log_info "Initializing FreeBSD kernel development environment setup for user $_username"

    # Define directory structure with proper FreeBSD conventions
    local _kernel_dev_dir="/home/${_username}/kernel-dev"
    local _src_dir="/usr/src"
    local _tools_dir="${_kernel_dev_dir}/tools"
    local _build_dir="${_kernel_dev_dir}/builds"
    local _patches_dir="${_kernel_dev_dir}/patches"
    local _docs_dir="${_kernel_dev_dir}/docs"
    local _tests_dir="${_kernel_dev_dir}/tests"

    # Validate user exists
    if ! pw user show "$_username" >/dev/null 2>&1; then
        log_error "User $_username does not exist"
        return 1
    }

    # Create directory structure with proper permissions
    log_info "Creating kernel development directory structure"
    local _directories=(
        "$_kernel_dev_dir"
        "$_tools_dir"
        "$_build_dir"
        "$_patches_dir"
        "$_docs_dir"
        "$_tests_dir"
    )

    for _dir in "${_directories[@]}"; do
        if ! mkdir -p "$_dir" 2>/dev/null; then
            log_error "Failed to create directory: $_dir"
            return 1
        fi
        chmod 750 "$_dir"
        chown "${_username}:wheel" "$_dir"
    done

    # Set up FreeBSD source tree if not present
    if [[ ! -d "$_src_dir" ]]; then
        log_info "FreeBSD source tree not found, initiating fetch"

        # Ensure we have Git installed for source management
        if ! pkg info git >/dev/null 2>&1; then
            log_info "Installing Git for source management"
            if ! pkg install -y git; then
                log_error "Failed to install Git"
                return 1
            fi
        }

        # Clone FreeBSD source repository
        log_info "Cloning FreeBSD source tree"
        if ! git clone --depth 1 https://git.FreeBSD.org/src.git "$_src_dir"; then
            log_error "Failed to clone FreeBSD source tree"
            return 1
        }
    }

    # Create custom kernel configuration template
    log_info "Creating custom kernel configuration template"
    local _kernel_conf="${_kernel_dev_dir}/CUSTOM"
    cat > "$_kernel_conf" << 'EOF'
#
# CUSTOM - Custom kernel configuration template for FreeBSD development
# Based on GENERIC with additional debugging options
#

include GENERIC

ident       CUSTOM

# Development and debugging options
makeoptions    DEBUG=-g            # Build kernel with debug symbols
makeoptions    WITH_CTF=1         # Build with CTF data for debugging

# Debugging Features
options     INVARIANTS           # Enable checks of internal consistency
options     INVARIANT_SUPPORT    # Support for INVARIANTS
options     WITNESS             # Enable locks/mutex debugging
options     WITNESS_SKIPSPIN    # Skip spin mutexes for witness
options     DIAGNOSTIC          # Additional diagnostic information
options     KDB                 # Enable kernel debugger support
options     DDB                 # Support for kernel debugger
options     GDB                 # GDB remote debugging support
options     DEADLKRES          # Enable deadlock resolver
options     KTRACE             # Kernel tracing support
options     STACK              # Stack traces in kernel messages
options     RACCT              # Resource Accounting
options     RCTL               # Resource Limits

# Memory debugging
options     DEBUG_MEMGUARD      # Memory corruption detection
options     DEBUGNET           # Remote kernel debugging over network

# Kernel crash dumps
options     EKCD               # Enable encrypted kernel crash dumps
options     KDTRACE_FRAME      # Ensure frames are compiled in
options     KDTRACE_HOOKS      # Kernel DTrace hooks
EOF

    # Create kernel build helper script
    log_info "Creating kernel build utility script"
    local _build_script="${_tools_dir}/build-kernel"
    cat > "$_build_script" << 'EOF'
#!/bin/sh
# FreeBSD Kernel Build Helper

set -e

KERNEL_CONFIG="$1"
BUILD_ID=$(date +%Y%m%d_%H%M%S)
BUILD_DIR="/usr/obj/kernel-builds/${BUILD_ID}"

if [ -z "$KERNEL_CONFIG" ]; then
    echo "Usage: $0 <kernel-config-file>"
    exit 1
fi

# Validate configuration file
if [ ! -f "$KERNEL_CONFIG" ]; then
    echo "Error: Kernel configuration file $KERNEL_CONFIG not found"
    exit 1
fi

# Create build directory
mkdir -p "${BUILD_DIR}"

# Build the kernel
cd /usr/src
make -j$(sysctl -n hw.ncpu) \
    KERNCONF=$(basename "$KERNEL_CONFIG") \
    buildkernel

# Install the kernel
make KERNCONF=$(basename "$KERNEL_CONFIG") \
    installkernel

echo "Kernel built and installed successfully"
echo "New kernel installed as /boot/kernel/kernel"
echo "Previous kernel backed up as /boot/kernel.old/kernel"
EOF

    chmod 750 "$_build_script"
    chown "${_username}:wheel" "$_build_script"

    # Create crash analysis tool
    log_info "Creating crash analysis utility"
    local _crash_script="${_tools_dir}/analyze-crash"
    cat > "$_crash_script" << 'EOF'
#!/bin/sh
# FreeBSD Kernel Crash Analysis Tool

DUMP="$1"
KERNEL="$2"

if [ -z "$DUMP" ] || [ -z "$KERNEL" ]; then
    echo "Usage: $0 <crash-dump> <kernel-image>"
    exit 1
fi

# Validate input files
if [ ! -f "$DUMP" ]; then
    echo "Error: Crash dump $DUMP not found"
    exit 1
fi

if [ ! -f "$KERNEL" ]; then
    echo "Error: Kernel image $KERNEL not found"
    exit 1
fi

# Run crash analysis
kgdb "$KERNEL" "$DUMP" << 'END'
bt
info threads
info registers
procstat
show malloc
show uma
END
EOF

    chmod 750 "$_crash_script"
    chown "${_username}:wheel" "$_crash_script"

    # Configure GDB for kernel debugging
    log_info "Setting up GDB configuration for kernel debugging"
    local _gdbinit="/home/${_username}/.gdbinit"
    cat > "$_gdbinit" << 'EOF'
# GDB configuration for FreeBSD kernel debugging

set print pretty on
set print object on
set print static-members on
set print vtbl on
set print demangle on
set demangle-style gnu-v3
set print sevenbit-strings off

# FreeBSD kernel debugging helpers
define lsproc
    set $p = allproc.lh_first
    while $p
        printf "pid %d: %s\n", $p->p_pid, $p->p_comm
        set $p = $p->p_list.le_next
    end
end

define lsthread
    set $td = allproc.lh_first
    while $td
        printf "thread %p: pid %d, tid %d, state %d\n", $td, $td->p_pid, $td->p_tid, $td->p_state
        set $td = $td->p_list.le_next
    end
end

# Add kernel symbols
add-auto-load-safe-path /boot/kernel
EOF

    chmod 640 "$_gdbinit"
    chown "${_username}:wheel" "$_gdbinit"

    # Install required development tools
    log_info "Installing kernel development tools"
    local _dev_packages=(
        devel/gdb
        devel/lldb
        devel/ctags
        devel/cscope
        devel/ccache
        devel/binutils
        devel/valgrind
    )

    for _package in "${_dev_packages[@]}"; do
        log_info "Installing $_package"
        if ! pkg install -y "$_package"; then
            log_warn "Failed to install $_package, continuing with setup"
        fi
    done

    # Create development environment documentation
    log_info "Creating development environment documentation"
    local _readme="${_docs_dir}/README.md"
    cat > "$_readme" << 'EOF'
# FreeBSD Kernel Development Environment

## Directory Structure

- `tools/`: Development and debugging utilities
- `builds/`: Kernel build outputs
- `patches/`: Custom kernel patches
- `docs/`: Documentation
- `tests/`: Kernel test suites

## Common Development Tasks

### Building a Custom Kernel

1. Copy CUSTOM to /usr/src/sys/amd64/conf/
2. Modify the configuration as needed
3. Run: ./tools/build-kernel /usr/src/sys/amd64/conf/CUSTOM

### Analyzing Kernel Crashes

1. Ensure crash dumps are configured in /etc/rc.conf:
   ```
   dumpdev="AUTO"
   dumpdir="/var/crash"
   ```
2. After a crash, use: ./tools/analyze-crash /var/crash/vmcore.X /boot/kernel/kernel

### Using DTrace for Kernel Analysis

1. Load the DTrace kernel module:
   ```
   kldload dtraceall
   ```
2. Use dtrace scripts from /usr/share/dtrace

### Kernel Debugging with GDB

1. Build kernel with debug symbols (included in CUSTOM config)
2. Use provided .gdbinit configuration
3. Connect with: gdb /boot/kernel/kernel

## Best Practices

1. Always keep a known-good kernel backup
2. Test changes in a virtual machine first
3. Use source control for kernel modifications
4. Document all configuration changes

## References

- FreeBSD Developers' Handbook: https://docs.freebsd.org/en/books/developers-handbook/
- FreeBSD Architecture Handbook: https://docs.freebsd.org/en/books/arch-handbook/
- FreeBSD Source Code: https://cgit.freebsd.org/src/
EOF

    chmod 644 "$_readme"
    chown "${_username}:wheel" "$_readme"

    # Add development environment to user's shell configuration
    log_info "Configuring shell environment"
    local _zshrc="/home/${_username}/.zshrc"
    cat >> "$_zshrc" << 'EOF'

# FreeBSD Kernel Development Environment
export KERNCONF=CUSTOM
export MAKEOBJDIRPREFIX=/usr/obj

# Kernel Development Aliases
alias ksrc='cd /usr/src'
alias kconfig='cd /usr/src/sys/amd64/conf'
alias kbuild='cd /usr/src && make buildkernel KERNCONF=CUSTOM'
alias kinstall='cd /usr/src && make installkernel KERNCONF=CUSTOM'
alias kdump='crashinfo -d /var/crash'
alias ktrace='ktrace -i'

# Development Tools
export PATH="${HOME}/kernel-dev/tools:${PATH}"
export CSCOPE_EDITOR="$(which vim)"
EOF

    # Set up kernel test framework
    log_info "Setting up kernel test framework"
    local _test_script="${_tests_dir}/run-tests"
    cat > "$_test_script" << 'EOF'
#!/bin/sh
# FreeBSD Kernel Test Framework

# Run kernel test suite
cd /usr/tests/sys
kyua test

# Run file system tests
cd /usr/tests/sys/fs
kyua test

# Run network stack tests
cd /usr/tests/sys/netinet
kyua test

# Generate HTML report
kyua report-html
EOF

    chmod 750 "$_test_script"
    chown "${_username}:wheel" "$_test_script"

    log_info "Kernel development environment setup completed successfully"
    log_info "Development environment documentation available at ${_docs_dir}/README.md"
    return 0
}

# Enhanced FreeBSD Directory Management System
# This module provides a comprehensive approach to creating and managing directory
# structures for development, testing, and container environments on FreeBSD systems.

# Define a structure to hold directory configurations
# This allows for easy modification and extension of directory structures
readonly DIRECTORY_STRUCTURES=(
    # Container environment structure
    "container:{
        base: /usr/local/container-env,
        owner: root:wheel,
        mode: 750,
        dirs: [
            {name: buildenv, mode: 750},
            {name: images, mode: 750},
            {name: compose, mode: 750},
            {name: scripts, mode: 755},
            {name: registry, mode: 750},
            {name: volumes, mode: 770},
            {name: configs, mode: 640},
            {name: templates, mode: 750},
            {name: security, mode: 700}
        ]
    }"

    # Testing environment structure
    "testing:{
        base: /usr/local/test-env,
        owner: root:wheel,
        mode: 750,
        dirs: [
            {name: unit, mode: 750},
            {name: integration, mode: 750},
            {name: performance, mode: 750},
            {name: security, mode: 700},
            {name: results, mode: 770},
            {name: scripts, mode: 755},
            {name: templates, mode: 750},
            {name: fixtures, mode: 750}
        ]
    }"

    # Development environment structure
    "development:{
        base: null,
        owner: null,
        mode: 750,
        dirs: [
            {name: projects, mode: 750},
            {name: toolchains, mode: 750},
            {name: scripts, mode: 755},
            {name: docs, mode: 750},
            {name: build, mode: 750},
            {name: samples, mode: 750},
            {name: libraries, mode: 750},
            {name: environments, mode: 750}
        ]
    }"
)

# Validate system requirements and configurations
validate_environment() {
    local _username="$1"

    # Verify root privileges
    if [[ $(id -u) -ne 0 ]]; then
        log_error "Directory creation requires root privileges"
        return 1
    }

    # Validate username
    if [[ -z "$_username" ]]; then
        log_error "Username parameter is required"
        return 1
    }

    # Verify user exists in system
    if ! pw user show "$_username" >/dev/null 2>&1; then
        log_error "User $_username does not exist in the system"
        return 1
    }

    # Check system resources
    local _min_space=102400  # 100MB in KB
    local _available_space

    # Check space in critical directories
    for _mount_point in /usr/local /home/"$_username" /var/log; do
        _available_space=$(df -k "$_mount_point" | awk 'NR==2 {print $4}')
        if [[ "${_available_space:-0}" -lt $_min_space ]]; then
            log_error "Insufficient disk space available on $_mount_point: ${_available_space}K"
            return 1
        }
    done

    return 0
}

# Create a single directory with proper permissions and validation
create_directory() {
    local _path="$1"
    local _owner="$2"
    local _mode="$3"
    local _name="$4"

    # Validate inputs
    if [[ -z "$_path" || -z "$_owner" || -z "$_mode" ]]; then
        log_error "Missing required parameters for directory creation"
        return 1
    }

    # Create directory with temp permissions
    if ! mkdir -p "$_path" 2>/dev/null; then
        log_error "Failed to create directory: $_path"
        return 1
    }

    # Set ownership and permissions
    if ! chown "$_owner" "$_path" 2>/dev/null; then
        log_error "Failed to set ownership on $_path to $_owner"
        return 1
    }

    if ! chmod "$_mode" "$_path" 2>/dev/null; then
        log_error "Failed to set mode $_mode on $_path"
        return 1
    }

    log_debug "Created directory $_name at $_path with mode $_mode and owner $_owner"
    return 0
}

# Create directory structure based on configuration
create_directory_structure() {
    local _structure="$1"
    local _username="$2"

    # Parse the structure configuration
    local _base_path _owner _mode
    eval "local _config=$_structure"

    # Handle development environment special case
    if [[ "${_config[base]}" == "null" ]]; then
        _base_path="/home/${_username}/development"
        _owner="${_username}:wheel"
    else
        _base_path="${_config[base]}"
        _owner="${_config[owner]}"
    fi

    _mode="${_config[mode]}"

    # Create base directory
    if ! create_directory "$_base_path" "$_owner" "$_mode" "base"; then
        return 1
    }

    # Create subdirectories
    local _success=0 _failed=0
    for _dir in "${_config[dirs][@]}"; do
        local _dir_path="${_base_path}/${_dir[name]}"
        local _dir_mode="${_dir[mode]}"

        if create_directory "$_dir_path" "$_owner" "$_dir_mode" "${_dir[name]}"; then
            _success=$((_success + 1))
        else
            _failed=$((_failed + 1))
            log_error "Failed to create ${_dir[name]} directory in $_base_path"
        fi
    done

    # Log creation summary
    log_info "Directory structure creation complete for $_base_path:"
    log_info "- Successfully created: $_success directories"
    log_info "- Failed to create: $_failed directories"

    return $((_failed > 0))
}

# Main function to create all directory structures
create_all_directories() {
    local _username="$1"

    log_info "Beginning directory structure creation process"

    # Validate environment first
    if ! validate_environment "$_username"; then
        log_error "Environment validation failed"
        return 1
    }

    # Track overall progress
    local _success=0 _failed=0

    # Create each directory structure
    for _structure in "${DIRECTORY_STRUCTURES[@]}"; do
        local _name="${_structure%%:*}"
        log_info "Creating $_name environment directories"

        if create_directory_structure "${_structure#*:}" "$_username"; then
            _success=$((_success + 1))
            log_info "$_name directory structure created successfully"
        else
            _failed=$((_failed + 1))
            log_error "Failed to create $_name directory structure"
        fi
    done

    # Generate final summary
    log_info "Directory creation process complete:"
    log_info "- Successfully created: $_success environments"
    log_info "- Failed to create: $_failed environments"

    # Create success marker file if everything succeeded
    if [[ $_failed -eq 0 ]]; then
        local _timestamp=$(date +%Y%m%d_%H%M%S)
        local _marker_file="/var/log/directory_setup_${_timestamp}.success"

        if echo "$_timestamp" > "$_marker_file"; then
            log_info "Created success marker: $_marker_file"
        fi

        return 0
    fi

    return 1
}

# Helper function to verify directory structure integrity
verify_directory_structure() {
    local _structure="$1"
    local _username="$2"

    eval "local _config=$_structure"

    # Handle development environment special case
    local _base_path
    if [[ "${_config[base]}" == "null" ]]; then
        _base_path="/home/${_username}/development"
    else
        _base_path="${_config[base]}"
    fi

    local _failed=0

    # Verify base directory
    if [[ ! -d "$_base_path" ]]; then
        log_error "Base directory $_base_path does not exist"
        _failed=$((_failed + 1))
    fi

    # Verify subdirectories and permissions
    for _dir in "${_config[dirs][@]}"; do
        local _dir_path="${_base_path}/${_dir[name]}"
        local _dir_mode="${_dir[mode]}"

        if [[ ! -d "$_dir_path" ]]; then
            log_error "Directory $_dir_path does not exist"
            _failed=$((_failed + 1))
            continue
        fi

        # Verify permissions
        local _actual_mode
        _actual_mode=$(stat -f "%Lp" "$_dir_path")
        if [[ "$_actual_mode" != "$_dir_mode" ]]; then
            log_error "Incorrect permissions on $_dir_path: expected $_dir_mode, got $_actual_mode"
            _failed=$((_failed + 1))
        fi
    done

    return $((_failed > 0))
}

#!/bin/zsh
# FreeBSD Container Environment Configuration
# This module sets up a comprehensive container development environment optimized
# for FreeBSD, with security hardening and proper resource isolation.

configure_container_environment() {
    local _username="$1"
    local _container_base="${2:-/usr/local/container-env}"

    log_info "Initializing FreeBSD container environment configuration"

    # Validate input parameters and environment
    if ! validate_container_prerequisites "$_username" "$_container_base"; then
        return 1
    }

    # Create a secure temporary directory for file operations
    local _temp_dir
    _temp_dir=$(mktemp -d -t container-setup.XXXXXX) || {
        log_error "Failed to create temporary directory"
        return 1
    }

    # Ensure temporary directory cleanup on exit
    trap 'rm -rf "$_temp_dir"' EXIT

    # Configuration steps with proper error handling
    local _steps=(
        "create_directory_structure"
        "configure_container_runtime"
        "setup_registry"
        "create_security_policies"
        "configure_networking"
        "install_management_scripts"
        "configure_user_environment"
    )

    local _failed=0
    for _step in "${_steps[@]}"; do
        log_info "Executing container setup step: $_step"
        if ! "$_step" "$_username" "$_container_base" "$_temp_dir"; then
            log_error "Failed during $_step"
            _failed=$((_failed + 1))
            # Critical steps that should abort on failure
            case "$_step" in
                "create_directory_structure"|"configure_container_runtime")
                    return 1
                    ;;
            esac
        fi
    done

    # Verify the setup
    if ! verify_container_setup "$_container_base"; then
        log_error "Container environment verification failed"
        return 1
    }

    if [[ $_failed -gt 0 ]]; then
        log_warn "Container environment setup completed with $_failed warnings"
    else
        log_info "Container environment setup completed successfully"
    fi

    print_setup_summary "$_container_base"
    return 0
}

validate_container_prerequisites() {
    local _username="$1"
    local _container_base="$2"

    # Verify root privileges
    if [[ $(id -u) -ne 0 ]]; then
        log_error "Container environment setup requires root privileges"
        return 1
    }

    # Validate username
    if ! pw user show "$_username" >/dev/null 2>&1; then
        log_error "User $_username does not exist"
        return 1
    }

    # Check required FreeBSD features
    if ! sysctl -n security.jail.allowed_sysvipc_objects >/dev/null 2>&1; then
        log_error "System does not support required jail features"
        return 1
    }

    # Verify required disk space (minimum 5GB)
    local _available_space
    _available_space=$(df -k "${_container_base%/*}" | awk 'NR==2 {print $4}')
    if [[ "${_available_space:-0}" -lt 5242880 ]]; then
        log_error "Insufficient disk space. Required: 5GB, Available: $((_available_space / 1024))MB"
        return 1
    }

    # Check for required utilities
    local _required_utils=(
        "bhyve"
        "ncat"
        "fetch"
        "jail"
        "zfs"
    )

    local _missing_utils=()
    for _util in "${_required_utils[@]}"; do
        if ! command -v "$_util" >/dev/null 2>&1; then
            _missing_utils+=("$_util")
        fi
    done

    if [[ ${#_missing_utils[@]} -gt 0 ]]; then
        log_error "Missing required utilities: ${_missing_utils[*]}"
        log_info "Install missing utilities using: pkg install -y ${_missing_utils[*]}"
        return 1
    }

    return 0
}

create_directory_structure() {
    local _username="$1"
    local _container_base="$2"

    local _directories=(
        "buildenv:750"
        "images:750"
        "compose:750"
        "scripts:755"
        "registry:750"
        "volumes:770"
        "configs:640"
        "templates:750"
        "security:700"
        "logs:750"
        "cache:750"
    )

    for _dir_spec in "${_directories[@]}"; do
        local _dir="${_dir_spec%:*}"
        local _mode="${_dir_spec#*:}"
        local _path="${_container_base}/${_dir}"

        if ! mkdir -p "$_path" 2>/dev/null; then
            log_error "Failed to create directory: $_path"
            return 1
        fi

        if ! chmod "$_mode" "$_path" 2>/dev/null; then
            log_error "Failed to set permissions on $_path"
            return 1
        }

        chown "root:wheel" "$_path"
        log_debug "Created directory $_dir with mode $_mode"
    done

    # Create special directories with different ownership
    chown "${_username}:wheel" "${_container_base}/volumes"
    chmod 770 "${_container_base}/volumes"

    return 0
}

configure_container_runtime() {
    local _username="$1"
    local _container_base="$2"
    local _temp_dir="$3"

    # Create runtime configuration
    cat > "${_temp_dir}/containers.conf" << 'EOL'
[containers]
# Network configuration optimized for FreeBSD
netns="jail"
network_backend="bridge"
network_interface_name="bridge0"

# Security settings
userns="host"
ipcns="private"
utsns="private"
cgroupns="host"
seccomp_profile="/usr/local/etc/containers/seccomp.json"

# Resource constraints
pids_limit = 4096
memory_limit = "8g"
cpu_shares = 1024
blkio_weight = 500

# Logging configuration
log_driver = "k8s-file"
log_size_max = 104857600  # 100MB
log_tag = "{{.Name}}_{{.ID}}_{{.ImageName}}"

[engine]
# Runtime configuration
runtime = "jail"
runtime_path = [
    "/usr/local/bin/jail-runtime",
    "/usr/local/sbin/jail-runtime"
]

# Storage configuration
graphroot = "/var/db/containers/storage"
runroot = "/var/run/containers"

[storage]
driver = "zfs"
graphroot = "/var/db/containers/storage"
runroot = "/var/run/containers"

[storage.options.zfs]
fsname = "zroot/containers"
mountopt = "noatime"

[network]
# Network configuration
cni_plugin_dirs = [
    "/usr/local/lib/cni",
    "/opt/cni/bin"
]
network_config_dir = "/usr/local/etc/cni/net.d"
EOL

    # Install configuration
    if ! install -m 644 "${_temp_dir}/containers.conf" /usr/local/etc/containers/containers.conf; then
        log_error "Failed to install container runtime configuration"
        return 1
    }

    return 0
}

setup_registry() {
    local _username="$1"
    local _container_base="$2"
    local _temp_dir="$3"

    # Create registry configuration
    cat > "${_temp_dir}/registry.yml" << 'EOL'
version: 0.1
log:
  level: info
  formatter: json
  fields:
    service: registry
    environment: development

storage:
  filesystem:
    rootdirectory: /var/db/registry
  cache:
    blobdescriptor: redis
  maintenance:
    uploadpurging:
      enabled: true
      age: 168h
      interval: 24h
      dryrun: false

http:
  addr: :5000
  host: https://localhost:5000
  secret: changeme
  tls:
    certificate: /usr/local/etc/registry/certs/registry.crt
    key: /usr/local/etc/registry/certs/registry.key

redis:
  addr: localhost:6379
  db: 0
  dialtimeout: 10ms
  readtimeout: 10ms
  writetimeout: 10ms
  pool:
    maxidle: 16
    maxactive: 64
    idletimeout: 300s

health:
  storagedriver:
    enabled: true
    interval: 10s
    threshold: 3
EOL

    # Install registry configuration
    install -m 640 "${_temp_dir}/registry.yml" "${_container_base}/configs/registry.yml"

    return 0
}

create_security_policies() {
    local _username="$1"
    local _container_base="$2"
    local _temp_dir="$3"

    # Create comprehensive seccomp profile
    cat > "${_temp_dir}/seccomp.json" << 'EOL'
{
    "defaultAction": "SCMP_ACT_ERRNO",
    "architectures": [
        "SCMP_ARCH_X86_64",
        "SCMP_ARCH_X86",
        "SCMP_ARCH_AARCH64"
    ],
    "syscalls": [
        {
            "names": [
                "accept",
                "accept4",
                "access",
                "arch_prctl",
                "bind",
                "brk",
                "chdir",
                "chmod",
                "chown",
                "clock_getres",
                "clock_gettime",
                "clock_nanosleep",
                "close",
                "connect",
                "copy_file_range",
                "creat",
                "dup",
                "dup2",
                "dup3",
                "epoll_create",
                "epoll_create1",
                "epoll_ctl",
                "epoll_ctl_old",
                "epoll_pwait",
                "epoll_wait",
                "epoll_wait_old",
                "eventfd",
                "eventfd2",
                "execve",
                "execveat",
                "exit",
                "exit_group",
                "faccessat",
                "fadvise64",
                "fchdir",
                "fchmod",
                "fchmodat",
                "fchown",
                "fchownat",
                "fcntl",
                "fdatasync",
                "flock",
                "fork",
                "fstatfs",
                "fsync",
                "ftruncate",
                "futex",
                "getcwd",
                "getdents",
                "getdents64",
                "getegid",
                "geteuid",
                "getgid",
                "getpeername",
                "getpgrp",
                "getpid",
                "getppid",
                "getpriority",
                "getrandom",
                "getresgid",
                "getresuid",
                "getrlimit",
                "getsockname",
                "getsockopt",
                "gettid",
                "gettimeofday",
                "getuid",
                "ioctl",
                "kill",
                "lseek",
                "lstat",
                "madvise",
                "mkdir",
                "mkdirat",
                "mmap",
                "mount",
                "mprotect",
                "munmap",
                "nanosleep",
                "newfstatat",
                "open",
                "openat",
                "pause",
                "pipe",
                "pipe2",
                "poll",
                "ppoll",
                "prctl",
                "pread64",
                "preadv",
                "prlimit64",
                "pselect6",
                "pwrite64",
                "pwritev",
                "read",
                "readahead",
                "readlink",
                "readlinkat",
                "readv",
                "recvfrom",
                "recvmsg",
                "rename",
                "renameat",
                "rmdir",
                "rt_sigaction",
                "rt_sigprocmask",
                "rt_sigqueueinfo",
                "rt_sigreturn",
                "rt_sigsuspend",
                "sched_yield",
                "seccomp",
                "select",
                "sendmsg",
                "sendto",
                "set_robust_list",
                "set_tid_address",
                "setgid",
                "setgroups",
                "setitimer",
                "setpgid",
                "setresgid",
                "setresuid",
                "setsid",
                "setsockopt",
                "setuid",
                "shmat",
                "shmctl",
                "shmdt",
                "shmget",
                "shutdown",
                "sigaltstack",
                "socket",
                "socketpair",
                "stat",
                "statfs",
                "symlink",
                "symlinkat",
                "sync",
                "sysinfo",
                "syslog",
                "tgkill",
                "time",
                "timerfd_create",
                "timerfd_gettime",
                "timerfd_settime",
                "times",
                "truncate",
                "umask",
                "uname",
                "unlink",
                "unlinkat",
                "utime",
                "utimensat",
                "wait4",
                "waitid",
                "write",
                "writev"
            ],
            "action": "SCMP_ACT_ALLOW"
        }
    ]
}
EOL

    # Install security policies
    install -m 600 "${_temp_dir}/seccomp.json" "${_container_base}/security/seccomp.json"

    return 0
}

configure_networking() {
    local _username="$1"
    local _container_base="$2"
    local _temp_dir="$3"

    # Create network initialization script
    cat > "${_temp_dir}/container-network" << 'EOL'
#!/bin/sh

# PROVIDE: container_network
# REQUIRE: NETWORKING
# KEYWORD: shutdown

. /etc/rc.subr

name="container_network"
rcvar="${name}_enable"
start_cmd="${name}_start"
stop_cmd="${name}_stop"

container_network_start()
{
    # Create bridge interface if it doesn't exist
    if ! ifconfig bridge0 >/dev/null 2>&1; then
        ifconfig bridge0 create
        ifconfig bridge0 up
    fi

    # Configure bridge with stable IP
    ifconfig bridge0 inet 10.88.0.1/16

    # Enable IP forwarding
    sysctl net.inet.ip.forwarding=1

    # Configure NAT if not already set
    pfctl -sm nat >/dev/null 2>&1 || {
        echo 'nat on $ext_if from 10.88.0.0/16 to any -> ($ext_if)' |
# Configure NAT if not already set
        pfctl -sm nat >/dev/null 2>&1 || {
            echo 'nat on $ext_if from 10.88.0.0/16 to any -> ($ext_if)' | \
            pfctl -N -f -
        }

        # Set up DNS for containers
        if [ ! -f /etc/resolvconf.conf.d/forward ]; then
            mkdir -p /etc/resolvconf.conf.d
            echo 'nameserver 8.8.8.8' > /etc/resolvconf.conf.d/forward
            echo 'nameserver 8.8.4.4' >> /etc/resolvconf.conf.d/forward
            resolvconf -u
        fi

        # Configure bridge firewall rules
        cat > /etc/pf.anchors/container-bridge << 'EOF'
# Allow DNS queries from containers
pass in quick on bridge0 proto { tcp udp } from 10.88.0.0/16 to any port 53

# Allow HTTP/HTTPS from containers
pass in quick on bridge0 proto tcp from 10.88.0.0/16 to any port { 80 443 }

# Allow container-to-container communication
pass in quick on bridge0 from 10.88.0.0/16 to 10.88.0.0/16

# Allow established connections back
pass in quick on bridge0 proto tcp from any to 10.88.0.0/16 flags S/SA keep state
EOF

        # Load the new anchor rules
        pfctl -a 'container-bridge' -f /etc/pf.anchors/container-bridge

        # Enable packet forwarding and configure sysctl parameters
        sysctl -w net.inet.ip.forwarding=1
        sysctl -w net.inet.tcp.tso=0
        sysctl -w net.inet.ip.check_interface=1
        sysctl -w net.inet.ip.process_options=0
    }

    container_network_stop()
    {
        # Remove firewall rules
        pfctl -a 'container-bridge' -F all

        # Destroy bridge interface
        ifconfig bridge0 destroy

        # Reset system parameters
        sysctl net.inet.ip.forwarding=0
    }

    load_rc_config $name
    run_rc_command "$1"
EOL

    # Install network initialization script
    install -m 555 "${_temp_dir}/container-network" /etc/rc.d/container-network

    # Configure CNI networking
    mkdir -p /usr/local/etc/cni/net.d
    cat > /usr/local/etc/cni/net.d/bridge.conflist << 'EOL'
{
    "cniVersion": "0.4.0",
    "name": "bridge",
    "plugins": [
        {
            "type": "bridge",
            "bridge": "bridge0",
            "isGateway": true,
            "ipMasq": true,
            "hairpinMode": true,
            "ipam": {
                "type": "host-local",
                "ranges": [
                    [
                        {
                            "subnet": "10.88.0.0/16",
                            "gateway": "10.88.0.1"
                        }
                    ]
                ],
                "routes": [
                    { "dst": "0.0.0.0/0" }
                ]
            }
        },
        {
            "type": "portmap",
            "capabilities": {"portMappings": true},
            "snat": true
        },
        {
            "type": "firewall",
            "backend": "iptables"
        }
    ]
}
EOL

    # Enable container networking in rc.conf
    if ! grep -q 'container_network_enable="YES"' /etc/rc.conf; then
        echo 'container_network_enable="YES"' >> /etc/rc.conf
    fi

    return 0
}

install_management_scripts() {
    local _username="$1"
    local _container_base="$2"
    local _temp_dir="$3"

    # Create build script with advanced security features
    cat > "${_temp_dir}/build-secure-container" << 'EOL'
#!/bin/sh
# Enhanced container build script with security scanning and best practices enforcement

set -e
set -u

IMAGE_NAME="$1"
VERSION="${2:-latest}"
CONTEXT_DIR="${3:-.}"

# Security configuration
TRIVY_SEVERITY="HIGH,CRITICAL"
DOCKLE_IGNORE="CIS-DI-0001,CIS-DI-0005,CIS-DI-0006"
GRYPE_SEVERITY="high,critical"

# Validation
if [ -z "$IMAGE_NAME" ]; then
    echo "Usage: $0 <image-name> [version] [context-dir]"
    exit 1
fi

# Build the container with security options
buildah build-using-dockerfile \
    --format docker \
    --security-opt seccomp=/usr/local/etc/containers/seccomp.json \
    --security-opt no-new-privileges \
    --cap-drop ALL \
    --cap-add SETFCAP \
    --cap-add MKNOD \
    --cap-add AUDIT_WRITE \
    --cap-add CHOWN \
    --cap-add NET_RAW \
    --cap-add NET_ADMIN \
    --cap-add SETGID \
    --cap-add SETUID \
    --cap-add DAC_OVERRIDE \
    --tag "${IMAGE_NAME}:${VERSION}" \
    "${CONTEXT_DIR}"

# Security scanning
if command -v trivy >/dev/null 2>&1; then
    echo "Scanning for vulnerabilities with Trivy..."
    trivy image \
        --severity "${TRIVY_SEVERITY}" \
        --no-progress \
        --ignore-unfixed \
        "${IMAGE_NAME}:${VERSION}"
fi

if command -v grype >/dev/null 2>&1; then
    echo "Scanning for vulnerabilities with Grype..."
    grype "${IMAGE_NAME}:${VERSION}" \
        --severity "${GRYPE_SEVERITY}" \
        --fail-on high
fi

if command -v dockle >/dev/null 2>&1; then
    echo "Checking Dockerfile best practices..."
    dockle \
        --ignore "${DOCKLE_IGNORE}" \
        --format json \
        "${IMAGE_NAME}:${VERSION}"
fi

# Tag successful build
if [ "$VERSION" != "latest" ]; then
    buildah tag "${IMAGE_NAME}:${VERSION}" "${IMAGE_NAME}:latest"
fi

echo "Build and security scanning completed successfully"
EOL

    # Install management scripts
    install -m 755 "${_temp_dir}/build-secure-container" "${_container_base}/scripts/"
    chown "${_username}:wheel" "${_container_base}/scripts/build-secure-container"

    return 0
}

configure_user_environment() {
    local _username="$1"
    local _container_base="$2"

    # Add container management aliases and functions to user's shell
    local _zshrc="/home/${_username}/.zshrc"
    cat >> "$_zshrc" << EOL

# Container Management Environment
export CONTAINER_BASE="${_container_base}"
export PATH="\${CONTAINER_BASE}/scripts:\${PATH}"

# Container Management Aliases and Functions
alias cb='build-secure-container'
alias cps='podman ps --format "table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Ports}}"'
alias cnet='sudo podman network ls'
alias cip='podman inspect -f "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}"'
alias clog='podman logs -f --tail=100'
alias cex='podman exec -it'
alias cst='podman stats --no-stream'
alias cin='podman inspect'
alias cdf='podman system df'
alias cprune='podman system prune -af --volumes'

# Enhanced container management functions
cstop() {
    if [ -z "$1" ]; then
        echo "Usage: cstop <container-name-or-id>"
        return 1
    fi
    podman stop "$1" && podman rm "$1"
}

crebuild() {
    if [ -z "$1" ]; then
        echo "Usage: crebuild <container-name>"
        return 1
    fi
    podman stop "$1" 2>/dev/null || true
    podman rm "$1" 2>/dev/null || true
    podman rmi "$1:latest" 2>/dev/null || true
    cb "$1"
}

csearch() {
    if [ -z "$1" ]; then
        echo "Usage: csearch <image-pattern>"
        return 1
    fi
    podman search --limit 25 --filter=is-official=true "$1"
}

clogs() {
    if [ -z "$1" ]; then
        echo "Usage: clogs <container-name-or-id>"
        return 1
    fi
    podman logs -f --since 1h --timestamps "$1"
}

cbackup() {
    local backup_dir="\${CONTAINER_BASE}/backups/\$(date +%Y%m%d)"
    mkdir -p "\$backup_dir"
    podman save -o "\$backup_dir/\$1.tar" "\$1"
    echo "Container image backed up to \$backup_dir/\$1.tar"
}
EOL

    # Set proper ownership
    chown "${_username}:wheel" "$_zshrc"
    chmod 644 "$_zshrc"

    return 0
}

verify_container_setup() {
    local _container_base="$1"
    local _failed=0

    # Verify directory structure
    local _required_dirs=(
        "buildenv"
        "images"
        "compose"
        "scripts"
        "registry"
        "volumes"
        "configs"
        "templates"
        "security"
    )

    for _dir in "${_required_dirs[@]}"; do
        if [ ! -d "${_container_base}/${_dir}" ]; then
            log_error "Missing required directory: ${_container_base}/${_dir}"
            _failed=$((_failed + 1))
        fi
    done

    # Verify configuration files
    local _required_files=(
        "/usr/local/etc/containers/containers.conf"
        "${_container_base}/configs/registry.yml"
        "${_container_base}/security/seccomp.json"
        "/etc/rc.d/container-network"
    )

    for _file in "${_required_files[@]}"; do
        if [ ! -f "$_file" ]; then
            log_error "Missing required file: $_file"
            _failed=$((_failed + 1))
        fi
    done

    # Verify network setup
    if ! ifconfig bridge0 >/dev/null 2>&1; then
        log_error "Bridge interface not configured"
        _failed=$((_failed + 1))
    fi

    # Verify permissions
    if [ ! -x "${_container_base}/scripts/build-secure-container" ]; then
        log_error "Build script not executable"
        _failed=$((_failed + 1))
    fi

    return $((_failed > 0))
}

print_setup_summary() {
    local _container_base="$1"

    cat << EOL

Container Environment Setup Summary
=================================

Base Directory: ${_container_base}

Available Commands:
-----------------
- cb <image>            : Build a secure container
- cps                   : List running containers
- cnet                  : List container networks
- clog <container>      : View container logs
- cex <container> <cmd> : Execute command in container
- cst                   : View container statistics
- cprune                : Clean up unused resources

Security Features:
----------------
- Seccomp profiles enabled
- Network isolation configured
- Security scanning integrated
- Resource limits enforced

Next Steps:
----------
1. Source your shell configuration: source ~/.zshrc
2. Build your first container: cb myapp
3. Review security policies in ${_container_base}/security
4. Check network configuration with 'cnet'

Documentation available in ${_container_base}/docs
EOL
}

#!/bin/zsh

# FreeBSD Testing Environment Configuration
# This module establishes a comprehensive testing environment optimized for FreeBSD
# systems, focusing on performance benchmarking, system analysis, and automated testing.

configure_testing_environment() {
    local _username="$1"
    local _test_base="${2:-/usr/local/test-env}"

    log_info "Initializing FreeBSD testing environment configuration"

    # First, validate the environment and prerequisites
    if ! validate_testing_prerequisites "$_username" "$_test_base"; then
        return 1
    }

    # Create a secure temporary directory for setup
    local _temp_dir
    _temp_dir=$(mktemp -d -t test-setup.XXXXXX) || {
        log_error "Failed to create temporary directory"
        return 1
    }

    # Ensure temporary directory cleanup
    trap 'rm -rf "$_temp_dir"' EXIT

    # Define our configuration steps
    local _steps=(
        "create_directory_structure"
        "configure_performance_tests"
        "setup_test_runners"
        "create_test_utilities"
        "configure_monitoring"
        "setup_reporting"
        "configure_user_environment"
    )

    # Execute configuration steps with proper error handling
    local _failed=0
    for _step in "${_steps[@]}"; do
        log_info "Executing testing setup step: $_step"
        if ! "$_step" "$_username" "$_test_base" "$_temp_dir"; then
            log_error "Failed during $_step"
            _failed=$((_failed + 1))
            if [[ "$_step" == "create_directory_structure" ]]; then
                return 1
            fi
        fi
    done

    # Verify the setup
    if ! verify_testing_setup "$_test_base"; then
        log_error "Testing environment verification failed"
        return 1
    }

    print_testing_summary "$_test_base"
    return $((_failed > 0))
}

validate_testing_prerequisites() {
    local _username="$1"
    local _test_base="$2"

    # Verify root privileges
    if [[ $(id -u) -ne 0 ]]; then
        log_error "Testing environment setup requires root privileges"
        return 1
    }

    # Validate username
    if ! pw user show "$_username" >/dev/null 2>&1; then
        log_error "User $_username does not exist"
        return 1
    }

    # Check for required testing tools
    local _required_tools=(
        "sysbench"
        "fio"
        "iperf3"
        "stress-ng"
        "netperf"
        "dtrace"
        "gstat"
        "vmstat"
        "procstat"
        "jq"
    )

    local _missing_tools=()
    for _tool in "${_required_tools[@]}"; do
        if ! command -v "$_tool" >/dev/null 2>&1; then
            _missing_tools+=("$_tool")
        fi
    done

    if [[ ${#_missing_tools[@]} -gt 0 ]]; then
        log_error "Missing required testing tools: ${_missing_tools[*]}"
        log_info "Install missing tools using: pkg install -y ${_missing_tools[*]}"
        return 1
    }

    # Check available disk space (minimum 20GB)
    local _available_space
    _available_space=$(df -k "${_test_base%/*}" | awk 'NR==2 {print $4}')
    if [[ "${_available_space:-0}" -lt 20971520 ]]; then
        log_error "Insufficient disk space. Required: 20GB, Available: $((_available_space / 1024 / 1024))GB"
        return 1
    }

    return 0
}

create_directory_structure() {
    local _username="$1"
    local _test_base="$2"

    # Define directory structure with permissions
    local _directories=(
        "performance:750:Tests for system performance analysis"
        "integration:750:Integration test suites"
        "unit:750:Unit test frameworks and tests"
        "security:700:Security and penetration tests"
        "results:770:Test results and reports"
        "scripts:755:Test execution scripts"
        "templates:750:Test templates and configurations"
        "fixtures:750:Test data and fixtures"
        "monitoring:750:System monitoring configurations"
        "reports:750:Generated test reports"
        "tools:755:Testing utilities and tools"
    )

    for _dir_spec in "${_directories[@]}"; do
        local _dir="${_dir_spec%%:*}"
        local _mode="${_dir_spec#*:}"
        _mode="${_mode%%:*}"
        local _desc="${_dir_spec##*:}"
        local _path="${_test_base}/${_dir}"

        if ! mkdir -p "$_path" 2>/dev/null; then
            log_error "Failed to create directory: $_path"
            return 1
        fi

        chmod "$_mode" "$_path"
        chown "root:wheel" "$_path"

        # Create README in each directory
        cat > "${_path}/README.md" << EOF
# ${_dir^} Directory

${_desc}

## Usage

This directory is part of the FreeBSD testing environment structure.
Created: $(date)
Permission Mode: ${_mode}

## Contents

EOF
    done

    # Set special permissions for results directory
    chown "${_username}:wheel" "${_test_base}/results"
    chmod 770 "${_test_base}/results"

    return 0
}

configure_performance_tests() {
    local _username="$1"
    local _test_base="$2"
    local _temp_dir="$3"

    # Create performance test configuration
    cat > "${_temp_dir}/performance.yaml" << 'EOL'
# FreeBSD System Performance Test Configuration
# This configuration defines comprehensive system performance tests

cpu_tests:
  stress_test:
    duration: 600
    threads:
      - 1
      - auto  # Uses number of CPU cores
      - max   # Uses 2x CPU cores
    operations:
      - matrix
      - prime
      - sort
      - crypto
    metrics:
      - cpu_usage
      - context_switches
      - interrupts
      - system_load

memory_tests:
  patterns:
    - sequential
    - random
    - stride
  block_sizes:
    - 4K
    - 64K
    - 1M
    - 16M
  operations:
    - read
    - write
    - copy
  metrics:
    - bandwidth
    - latency
    - page_faults
    - cache_misses

disk_tests:
  file_sizes:
    - 1G
    - 10G
  block_sizes:
    - 4K
    - 64K
    - 1M
  patterns:
    - sequential
    - random
  operations:
    - read
    - write
    - mixed
  filesystems:
    - ufs
    - zfs
    - tmpfs
  metrics:
    - iops
    - throughput
    - latency
    - queue_depth

network_tests:
  protocols:
    - tcp
    - udp
  packet_sizes:
    - 64    # Minimum
    - 1500  # Standard MTU
    - 9000  # Jumbo frames
  tests:
    - bandwidth
    - latency
    - connection_rate
    - packet_loss
  configurations:
    - single_stream
    - multi_stream
    - bidirectional

monitoring:
  interval: 1
  metrics:
    - cpu_usage
    - memory_usage
    - disk_io
    - network_io
    - system_load
    - process_count
    - interrupt_rate
    - context_switches
EOL

    # Install performance configuration
    install -m 640 "${_temp_dir}/performance.yaml" "${_test_base}/performance/config.yaml"
    chown "root:wheel" "${_test_base}/performance/config.yaml"

    return 0
}

setup_test_runners() {
    local _username="$1"
    local _test_base="$2"
    local _temp_dir="$3"

    # Create the main test execution script
    cat > "${_temp_dir}/run-performance-tests" << 'EOL'
#!/bin/sh
# FreeBSD Performance Test Runner
# This script executes comprehensive system performance tests and generates
# detailed reports with DTrace integration for deep system analysis.

set -e
set -u

# Initialize test environment
init_test_environment() {
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local results_dir="${TEST_BASE}/results/${timestamp}"
    mkdir -p "${results_dir}"

    # Create result subdirectories
    mkdir -p "${results_dir}"/{cpu,memory,disk,network,system}

    # Initialize DTrace scripts
    setup_dtrace_monitoring "${results_dir}"

    echo "${results_dir}"
}

# Configure DTrace monitoring
setup_dtrace_monitoring() {
    local results_dir="$1"

    # Create DTrace script for system analysis
    cat > "${results_dir}/monitor.d" << 'DTRACE'
#!/usr/sbin/dtrace -s

#pragma D option quiet
#pragma D option dynvarsize=16m
#pragma D option bufsize=16m

dtrace:::BEGIN
{
    printf("Starting system monitoring...\n");
}

profile:::tick-1sec
{
    @cpu_busy = sum(cpu::busy-cpu:tick-1sec:count);
    @mem_ops = sum(vminfo::vm_faults:count);
    @disk_ops = sum(io:::start:count);
    @net_pkts = sum(ip:::send:count);
}

profile:::tick-10sec
{
    printf("\nSystem Statistics @ %Y\n", walltimestamp);
    printf("CPU Usage: %@d\n", @cpu_busy);
    printf("Memory Operations: %@d\n", @mem_ops);
    printf("Disk Operations: %@d\n", @disk_ops);
    printf("Network Packets: %@d\n", @net_pkts);

    trunc(@cpu_busy);
    trunc(@mem_ops);
    trunc(@disk_ops);
    trunc(@net_pkts);
}

dtrace:::END
{
    printf("Monitoring complete.\n");
}
DTRACE

    chmod 755 "${results_dir}/monitor.d"
}

# Execute CPU performance tests
run_cpu_tests() {
    local results_dir="$1"

    echo "Running CPU performance tests..."

    # Multiple test scenarios
    for threads in 1 $(sysctl -n hw.ncpu) $(( $(sysctl -n hw.ncpu) * 2 )); do
        stress-ng --cpu "$threads" \
                 --cpu-method all \
                 --metrics-brief \
                 --timeout 60s \
                 --log-file "${results_dir}/cpu/cpu_test_${threads}.log"

        # Extract and format results
        awk '/cpu/ {print $0}' "${results_dir}/cpu/cpu_test_${threads}.log" \
            >> "${results_dir}/cpu/summary.txt"
    done
}

# Execute memory performance tests
run_memory_tests() {
    local results_dir="$1"

    echo "Running memory performance tests..."

    for size in 4K 64K 1M 16M; do
        sysbench memory \
            --memory-block-size="$size" \
            --memory-total-size=100G \
            --memory-access-mode=seq \
            run > "${results_dir}/memory/memory_test_${size}.log"

        # Extract results
        awk '/transferred/ {print $4, $5}' \
            "${results_dir}/memory/memory_test_${size}.log" \
            >> "${results_dir}/memory/summary.txt"
    done
}

# Execute disk performance tests
run_disk_tests() {
    local results_dir="$1"

    echo "Running disk performance tests..."

    local test_file="/tmp/fio_test"

    for bs in 4k 64k 1M; do
        for rw in read write randread randwrite; do
            fio --filename="$test_file" \
                --direct=1 \
                --rw="$rw" \
                --bs="$bs" \
                --ioengine=posixaio \
                --iodepth=16 \
                --group_reporting \
                --name="test_${rw}_${bs}" \
                --size=1G \
                --runtime=60 \
                --numjobs=4 \
                --output="${results_dir}/disk/disk_test_${rw}_${bs}.log"
        done
    done

    rm -f "$test_file"

    # Compile results
    for log in "${results_dir}/disk/disk_test_"*".log"; do
        awk '/READ|WRITE/ {print $0}' "$log" >> "${results_dir}/disk/summary.txt"
    done
}

# Execute network performance tests
run_network_tests() {
    local results_dir="$1"

    echo "Running network performance tests..."

    # Start iperf3 server
    iperf3 -s -D

    # Run various network tests
    for protocol in TCP UDP; do
        for parallel in 1 4 8; do
            iperf3 -c localhost \
                   -p 5201 \
                   -t 30 \
                   -P "$parallel" \
                   ${protocol:+-u} \
                   -J > "${results_dir}/network/network_test_${protocol}_${parallel}.json"
        done
    done

    # Stop iperf3 server
    pkill iperf3

    # Compile results
    for result in "${results_dir}/network/network_test_"*".json"; do
        jq -r '.end.sum_received.bits_per_second' "$result" \
            | awk "{printf \"${result##*/}: %.2f Mbps\n\", \$1/1000000}" \
            >> "${results_dir}/network/summary.txt"
    done
}

# Generate comprehensive report
generate_report() {
    local results_dir="$1"

    {
        echo "FreeBSD System Performance Test Report"
        echo "====================================="
        echo "Generated: $(date)"
        echo
        echo "System Information"
        echo "-----------------"
        echo "OS: $(uname -a)"
        echo "CPU: $(sysctl -n hw.model)"
        echo "Cores: $(sysctl -n hw.ncpu)"
        echo "Memory: $(sysctl -n hw.physmem | awk '{printf "%.2f GB\n", $1/1024/1024/1024}')"
        echo
        echo "Test Results Summary"
        echo "-------------------"
        echo
        echo "CPU Performance:"
        cat "${results_dir}/cpu/summary.txt"
        echo
        echo "Memory Performance:"
        cat "${results_dir}/memory/summary.txt"
        echo
        echo "Disk Performance:"
        cat "${results_dir}/disk/summary.txt"
        echo
        echo "Network Performance:"
        cat "${results_dir}/network/summary.txt"
        echo
        echo "System Monitoring Data"
        echo "--------------------"
        echo "DTrace analysis results are available in: ${results_dir}/dtrace_analysis.log"
        echo
        echo "Recommendations"
        echo "--------------"
        analyze_results "${results_dir}"
    } > "${results_dir}/report.txt"

    # Create a symlink to the latest report
    ln -sf "${results_dir}/report.txt" "${TEST_BASE}/results/latest_report.txt"
}

# Analyze test results and provide recommendations
analyze_results() {
    local results_dir="$1"
    local recommendations=()

    # Analyze CPU performance
    local cpu_busy
    cpu_busy=$(awk '/cpu_busy/ {sum += $2; count++} END {print sum/count}' "${results_dir}/cpu/summary.txt")
    if [ "${cpu_busy:-0}" -gt 80 ]; then
        recommendations+=("CPU utilization is high (${cpu_busy}%). Consider investigating process priorities and CPU-bound tasks.")
    fi

    # Analyze memory performance
    local memory_bandwidth
    memory_bandwidth=$(awk '/copied/ {sum += $1; count++} END {print sum/count}' "${results_dir}/memory/summary.txt")
    if [ "${memory_bandwidth:-0}" -lt 5000 ]; then
        recommendations+=("Memory bandwidth appears low. Consider checking memory configuration and placement.")
    fi

    # Analyze disk performance
    local disk_iops
    disk_iops=$(awk '/IOPS/ {sum += $2; count++} END {print sum/count}' "${results_dir}/disk/summary.txt")
    if [ "${disk_iops:-0}" -lt 1000 ]; then
        recommendations+=("Disk I/O performance could be improved. Consider checking disk scheduler and file system parameters.")
    fi

    # Analyze network performance
    local network_throughput
    network_throughput=$(awk '{sum += $2; count++} END {print sum/count}' "${results_dir}/network/summary.txt")
    if [ "${network_throughput:-0}" -lt 100 ]; then
        recommendations+=("Network performance is below expected levels. Consider reviewing network stack tuning.")
    }

    # Print recommendations
    echo "Based on test results, here are the system optimization recommendations:"
    echo
    for recommendation in "${recommendations[@]}"; do
        echo "- $recommendation"
    done
}

# Main execution function
main() {
    local results_dir
    results_dir=$(init_test_environment) || exit 1

    # Start system monitoring
    dtrace -s "${results_dir}/monitor.d" > "${results_dir}/dtrace_analysis.log" 2>/dev/null &
    local dtrace_pid=$!

    # Run performance tests
    run_cpu_tests "$results_dir"
    run_memory_tests "$results_dir"
    run_disk_tests "$results_dir"
    run_network_tests "$results_dir"

    # Stop DTrace monitoring
    kill $dtrace_pid

    # Generate final report
    generate_report "$results_dir"

    echo "Performance tests completed. Report available at: ${results_dir}/report.txt"
}

# Execute main function with error handling
if ! main "$@"; then
    echo "Error: Performance tests failed to complete successfully"
    exit 1
fi
EOL

    # Install the test runner script
    install -m 755 "${_temp_dir}/run-performance-tests" "${_test_base}/scripts/"
    chown "root:wheel" "${_test_base}/scripts/run-performance-tests"

    # Create a test data generator for consistent test fixtures
    cat > "${_temp_dir}/generate-test-data" << 'EOL'
#!/bin/sh
# Test Data Generator for FreeBSD Testing Environment

set -e
set -u

FIXTURES_DIR="${TEST_BASE}/fixtures"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Generate various sizes of random data
generate_random_data() {
    local sizes=("1M" "10M" "100M" "1G")

    for size in "${sizes[@]}"; do
        dd if=/dev/random bs=1M count="${size%[A-Z]*}" \
           of="${FIXTURES_DIR}/random_${size}.dat" 2>/dev/null
    done
}

# Generate structured test data in various formats
generate_structured_data() {
    # JSON test data
    cat > "${FIXTURES_DIR}/test_data.json" << 'EOF'
{
    "test_suite": "performance_tests",
    "version": "1.0",
    "test_cases": [
        {
            "name": "cpu_test",
            "parameters": {
                "threads": [1, 2, 4, 8],
                "duration": 300,
                "operations": ["integer", "floating", "matrix"]
            }
        },
        {
            "name": "memory_test",
            "parameters": {
                "sizes": ["4K", "64K", "1M"],
                "patterns": ["sequential", "random"],
                "operations": ["read", "write", "copy"]
            }
        }
    ]
}
EOF

    # CSV test data
    cat > "${FIXTURES_DIR}/test_data.csv" << 'EOF'
test_id,name,type,parameters,expected_result
1,cpu_basic,performance,"threads=1,duration=60",pass
2,memory_sequential,performance,"size=1M,pattern=seq",pass
3,disk_random,performance,"size=4K,pattern=random",pass
4,network_bandwidth,performance,"protocol=tcp,size=1500",pass
EOF

    # YAML test data
    cat > "${FIXTURES_DIR}/test_data.yaml" << 'EOF'
test_suite:
  name: system_performance
  version: 1.0
  tests:
    - name: cpu_test
      type: performance
      parameters:
        threads: [1, 2, 4, 8]
        duration: 300
        operations:
          - integer
          - floating
          - matrix
    - name: memory_test
      type: performance
      parameters:
        sizes: [4K, 64K, 1M]
        patterns:
          - sequential
          - random
        operations:
          - read
          - write
          - copy
EOF
}

# Generate system-specific test data
generate_system_data() {
    # Capture system configuration
    sysctl -a > "${FIXTURES_DIR}/sysctl_${TIMESTAMP}.conf"

    # Capture hardware information
    pciconf -lv > "${FIXTURES_DIR}/pciconf_${TIMESTAMP}.txt"

    # Capture loader configuration
    cp /boot/loader.conf "${FIXTURES_DIR}/loader_${TIMESTAMP}.conf"
}

# Main execution
main() {
    # Create fixtures directory if it doesn't exist
    mkdir -p "${FIXTURES_DIR}"

    echo "Generating test data..."

    # Generate all test data types
    generate_random_data
    generate_structured_data
    generate_system_data

    # Set appropriate permissions
    chmod 644 "${FIXTURES_DIR}"/*
    chown -R root:wheel "${FIXTURES_DIR}"

    echo "Test data generation completed successfully"
    echo "Test data available in: ${FIXTURES_DIR}"
}

# Execute main function
main "$@"
EOL

    # Install the test data generator
    install -m 755 "${_temp_dir}/generate-test-data" "${_test_base}/scripts/"
    chown "root:wheel" "${_test_base}/scripts/generate-test-data"

    return 0
}

create_test_utilities() {
    local _username="$1"
    local _test_base="$2"
    local _temp_dir="$3"

    # Create test analysis utilities
    cat > "${_temp_dir}/analyze-results" << 'EOL'
#!/bin/sh
# Test Results Analysis Utility

set -e
set -u

RESULTS_DIR="${TEST_BASE}/results"

# Analyze test results and generate insights
analyze_test_results() {
    local test_dir="$1"
    local report_file="${test_dir}/analysis_report.txt"

    {
        echo "Test Results Analysis"
        echo "===================="
        echo "Generated: $(date)"
        echo

        echo "Performance Metrics"
        echo "-----------------"
        analyze_performance_metrics "$test_dir"

        echo
        echo "System Resource Usage"
        echo "-------------------"
        analyze_resource_usage "$test_dir"

        echo
        echo "Comparison with Baseline"
        echo "----------------------"
        compare_with_baseline "$test_dir"

        echo
        echo "Recommendations"
        echo "--------------"
        generate_recommendations "$test_dir"
    } > "$report_file"

    echo "Analysis complete. Report available at: $report_file"
}

# Main execution
main() {
    if [ $# -eq 0 ]; then
        # Use latest test results if no directory specified
        latest_dir=$(ls -td "${RESULTS_DIR}"/*/ | head -1)
        if [ -z "$latest_dir" ]; then
            echo "No test results found"
            exit 1
        fi
        analyze_test_results "$latest_dir"
    else
        analyze_test_results "$1"
    fi
}

main "$@"
EOL

    # Install analysis utility
    install -m 755 "${_temp_dir}/analyze-results" "${_test_base}/tools/"
    chown "root:wheel" "${_test_base}/tools/analyze-results"

    return 0
}

configure_monitoring() {
    local _username="$1"
    local _test_base="$2"
    local _temp_dir="$3"

    # Create monitoring configuration
    cat > "${_temp_dir}/monitoring.yaml" << 'EOL'
# Test Environment Monitoring Configuration

intervals:
  default: 1
  detailed: 0.1
  extended: 5

metrics:
  system:
    - cpu_usage
    - memory_usage
    - disk_io
    - network_io
    - context_switches
    - interrupts
    - syscalls

  process:
    - cpu_usage
    - memory_usage
    - file_descriptors
    - threads

  custom_events:
    - test_start
    - test_end
    - error_condition
    - threshold_exceeded

thresholds:
  cpu_usage: 80
  memory_usage: 90
  disk_usage: 85
  load_average: 8

alerts:
  methods:
    - log
    - email
  thresholds:
    critical:
      cpu_usage: 95
      memory_usage: 95
      disk_usage: 95
    warning:
      cpu_usage: 80
      memory_usage: 80
      disk_usage: 80
EOL

    # Install monitoring configuration
    install -m 640 "${_temp_dir}/monitoring.yaml" "${_test_base}/monitoring/"
    chown "root:wheel" "${_test_base}/monitoring/monitoring.yaml"

    return 0
}

setup_reporting() {
    local _username="$1"
    local _test_base="$2"
    local _temp_dir="$3"

    # Create reporting templates
    mkdir -p "${_test_base}/templates/reports"

    # Performance test report template
    cat > "${_test_base}/templates/reports/performance.md" << 'EOL'
# Performance Test Report

## Test Information
- Test Date: {{date}}
- Test Duration: {{duration}}
- System: {{system_info}}

## Performance Metrics

### CPU Performance
{{cpu_metrics}}

### Memory Performance
{{memory_metrics}}

### Disk I/O Performance
{{disk_metrics}}

### Network Performance
{{network_metrics}}

## Analysis and Recommendations
{{analysis}}

## System Configuration
{{system_config}}

## Test Environment
{{test_environment}}
EOL

    # Create reporting utilities
    cat > "${_temp_dir}/generate-report" << 'EOL'
#!/bin/sh
# Test Report Generator

set -e
set -u

TEMPLATES_DIR="${TEST_BASE}/templates/reports"
RESULTS_DIR="${TEST_BASE}/results"

# Generate a test report using the specified template
generate_report() {
    local results_dir="$1"
    local template="$2"
    local output_file="${results_dir}/report.md"

    # Process template and generate report
    sed \
        -e "s/{{date}}/$(date)/" \
        -e "s/{{system_info}}/$(uname -a)/" \
        -e "s/{{duration}}/$(get_test_duration "$results_dir")/" \
        -e "/{{cpu_metrics}}/r ${results_dir}/cpu/summary.txt" \
        -e "/{{memory_metrics}}/r ${results_dir}/memory/summary.txt" \
        -e "/{{disk_metrics}}/r ${results_dir}/disk/summary.txt" \
        -e "/{{network_metrics}}/r ${results_dir}/network/summary.txt" \
        -e "/{{analysis}}/r ${results_dir}/analysis.txt" \
        -e "/{{system_config}}/r ${results_dir}/system.txt" \
        -e "/{{test_environment}}/r ${results_dir}/environment.txt" \
        "$template" > "$output_file"

    echo "Report generated: $output_file"
}

# Main execution
main() {
    if [ $# -eq 0 ]; then
        # Use latest results if no directory specified
        latest_dir=$(ls -td "${RESULTS_DIR}"/*/ | head -1)
        if [ -z "$latest_dir" ]; then
            echo "No test results found"
            exit 1
        fi
        generate_report "$latest_dir" "${TEMPLATES_DIR}/performance.md"
    else
        generate_report "$1" "${TEMPLATES_DIR}/performance.md"
    fi
}

main "$@"
EOL

    # Install reporting utility
    install -m 755 "${_temp_dir}/generate-report" "${_test_base}/tools/"
    chown "root:wheel" "${_test_base}/tools/generate-report"

    return 0
}

configure_user_environment() {
    local _username="$1"
    local _test_base="$2"

    # Add testing environment configuration to user's shell
    local _zshrc="/home/${_username}/.zshrc"
    cat >> "$_zshrc" << EOL

# Testing Environment Configuration
export TEST_BASE="${_test_base}"
export PATH="\${TEST_BASE}/tools:\${TEST_BASE}/scripts:\${PATH}"

# Test Environment Aliases
alias run-tests='${_test_base}/scripts/run-performance-tests'
alias analyze-tests='${_test_base}/tools/analyze-results'
alias gen-report='${_test_base}/tools/generate-report'
alias view-report='less \$(ls -t ${_test_base}/results/*/report.txt | head -1)'
alias monitor-tests='tail -f ${_test_base}/results/latest/monitor.log'
alias test-clean='find ${_test_base}/results -mtime +30 -delete'

# Test Environment Functions
test_info() {
    echo "Testing Environment Information"
    echo "-----------------------------"
    echo "Base Directory: ${_test_base}"
    echo "Latest Results: \$(ls -td ${_test_base}/results/*/ | head -1)"
    echo "Available Tests: \$(ls ${_test_base}/scripts/run-*)"
}
EOL

    # Set proper ownership
    chown "${_username}:wheel" "$_zshrc"
    chmod 644 "$_zshrc"

    # Create additional testing utility functions
    cat >> "$_zshrc" << 'EOL'

# Test result analysis function
analyze_last_test() {
    local latest_results=$(ls -td ${TEST_BASE}/results/*/ | head -1)
    if [[ -z "$latest_results" ]]; then
        echo "No test results found"
        return 1
    }

    echo "Analyzing results from: $latest_results"
    echo "=================================="

    # Summary statistics
    echo "Test Duration: $(stat -f %m "$latest_results")"
    echo "CPU Statistics:"
    awk '/cpu/ {print $0}' "${latest_results}/cpu/summary.txt"

    echo "Memory Statistics:"
    awk '/memory/ {print $0}' "${latest_results}/memory/summary.txt"

    echo "Disk Statistics:"
    awk '/disk/ {print $0}' "${latest_results}/disk/summary.txt"

    echo "Network Statistics:"
    awk '/network/ {print $0}' "${latest_results}/network/summary.txt"
}

# Test environment maintenance function
maintain_test_env() {
    echo "Performing test environment maintenance..."

    # Clean old results (keep last 30 days by default)
    find ${TEST_BASE}/results -mtime +30 -delete

    # Verify directory permissions
    find ${TEST_BASE} -type d -exec chmod 750 {} \;
    find ${TEST_BASE}/results -type d -exec chmod 770 {} \;

    # Reset ownership
    chown -R root:wheel ${TEST_BASE}
    chown -R ${USER}:wheel ${TEST_BASE}/results

    # Clean temporary files
    find ${TEST_BASE} -name "*.tmp" -delete
    find ${TEST_BASE} -name "*.log" -mtime +7 -delete

    echo "Maintenance completed successfully"
}

# Test execution wrapper function
run_test_suite() {
    local test_type="$1"
    local test_options="${2:-}"
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local log_file="${TEST_BASE}/results/${timestamp}_${test_type}.log"

    echo "Starting test suite: $test_type"
    echo "Options: ${test_options:-none}"
    echo "Log file: $log_file"

    # Initialize test environment
    if ! initialize_test_env "$test_type"; then
        echo "Failed to initialize test environment"
        return 1
    }

    # Execute test with logging
    if ${TEST_BASE}/scripts/run-"$test_type"-tests $test_options > "$log_file" 2>&1; then
        echo "Test suite completed successfully"
        analyze_last_test
    else
        echo "Test suite failed. Check $log_file for details"
        return 1
    fi
}

# Test environment verification function
verify_test_env() {
    local status=0
    local required_dirs=(
        "performance"
        "integration"
        "unit"
        "security"
        "results"
        "scripts"
        "templates"
        "fixtures"
        "monitoring"
        "reports"
        "tools"
    )

    echo "Verifying test environment..."

    # Check directory structure
    for dir in "${required_dirs[@]}"; do
        if [[ ! -d "${TEST_BASE}/$dir" ]]; then
            echo "Missing required directory: $dir"
            status=1
        fi
    done

    # Verify permissions
    if ! find "${TEST_BASE}" -type d -perm 750 >/dev/null 2>&1; then
        echo "Incorrect directory permissions detected"
        status=1
    fi

    # Check for required tools
    local required_tools=(
        "sysbench"
        "fio"
        "iperf3"
        "dtrace"
    )

    for tool in "${required_tools[@]}"; do
        if ! command -v "$tool" >/dev/null 2>&1; then
            echo "Missing required tool: $tool"
            status=1
        fi
    done

    # Verify configuration files
    local required_configs=(
        "performance/config.yaml"
        "monitoring/monitoring.yaml"
        "templates/reports/performance.md"
    )

    for config in "${required_configs[@]}"; do
        if [[ ! -f "${TEST_BASE}/$config" ]]; then
            echo "Missing configuration file: $config"
            status=1
        fi
    done

    if [[ $status -eq 0 ]]; then
        echo "Test environment verification passed"
    else
        echo "Test environment verification failed"
    fi

    return $status
}

# Test report generation helper
generate_test_report() {
    local test_id="$1"
    local template="${2:-performance}"
    local results_dir="${TEST_BASE}/results/${test_id}"

    if [[ ! -d "$results_dir" ]]; then
        echo "Test results not found: $test_id"
        return 1
    fi

    # Generate comprehensive report
    ${TEST_BASE}/tools/generate-report "$results_dir" "$template"

    # Create performance visualizations if gnuplot is available
    if command -v gnuplot >/dev/null 2>&1; then
        generate_performance_graphs "$results_dir"
    fi

    echo "Report generated successfully"
}

# Initialize test environment
initialize_test_env() {
    local test_type="$1"
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local test_dir="${TEST_BASE}/results/${timestamp}_${test_type}"

    # Create test directory structure
    mkdir -p "$test_dir"/{data,logs,results}

    # Initialize monitoring
    setup_monitoring "$test_dir"

    # Prepare test fixtures
    prepare_test_fixtures "$test_type" "$test_dir"

    echo "$test_dir"
}
EOL

    # Create test environment documentation
    cat > "${_test_base}/README.md" << 'EOL'
# FreeBSD Testing Environment

This testing environment provides a comprehensive framework for system performance
testing, monitoring, and analysis on FreeBSD systems.

## Directory Structure

- `performance/`: Performance test configurations and benchmarks
- `integration/`: Integration test suites
- `unit/`: Unit test frameworks and tests
- `security/`: Security and penetration tests
- `results/`: Test results and reports
- `scripts/`: Test execution scripts
- `templates/`: Test templates and configurations
- `fixtures/`: Test data and fixtures
- `monitoring/`: System monitoring configurations
- `reports/`: Generated test reports
- `tools/`: Testing utilities and tools

## Usage

1. Initialize the environment:
   ```sh
   source ~/.zshrc
   ```

2. Run performance tests:
   ```sh
   run-tests
   ```

3. Analyze results:
   ```sh
   analyze-tests
   ```

4. Generate reports:
   ```sh
   gen-report
   ```

## Maintenance

Regular maintenance can be performed using:
```sh
maintain_test_env
```

## Configuration

Test configurations are stored in YAML format in their respective directories.
Modify these files to adjust test parameters and thresholds.

## Monitoring

The environment includes comprehensive system monitoring during test execution.
Monitor logs are available in the results directory for each test run.

## Reporting

Test reports are generated in Markdown format and include:
- Performance metrics
- System statistics
- Resource utilization
- Recommendations

## Security

All test artifacts are created with appropriate permissions and ownership.
Security tests are isolated and require elevated privileges to execute.

## Support

For issues or questions, consult the FreeBSD documentation or contact system
administration.
EOL

    # Ensure documentation has proper ownership and permissions
    chown "${_username}:wheel" "${_test_base}/README.md"
    chmod 644 "${_test_base}/README.md"

    return 0
}

verify_testing_setup() {
    local _test_base="$1"
    local _failed=0

    # Verify directory structure
    for _dir in performance integration unit security results scripts templates fixtures monitoring reports tools; do
        if [[ ! -d "${_test_base}/${_dir}" ]]; then
            log_error "Missing required directory: ${_test_base}/${_dir}"
            _failed=$((_failed + 1))
        fi
    done

    # Verify script permissions
    for _script in "${_test_base}/scripts"/*; do
        if [[ -f "$_script" && ! -x "$_script" ]]; then
            log_error "Script missing executable permission: $_script"
            _failed=$((_failed + 1))
        fi
    done

    # Verify configuration files
    for _config in performance/config.yaml monitoring/monitoring.yaml; do
        if [[ ! -f "${_test_base}/${_config}" ]]; then
            log_error "Missing configuration file: ${_test_base}/${_config}"
            _failed=$((_failed + 1))
        fi
    done

    return $((_failed > 0))
}

print_testing_summary() {
    local _test_base="$1"

    cat << EOL

Testing Environment Setup Summary
===============================

Base Directory: ${_test_base}

Available Commands:
----------------
run-tests       : Execute performance test suite
analyze-tests   : Analyze test results
gen-report      : Generate test reports
view-report     : View latest test report
monitor-tests   : Monitor ongoing tests
test-clean      : Clean old test results

Utility Functions:
---------------
test_info()         : Display environment information
analyze_last_test() : Analyze most recent test results
maintain_test_env() : Perform environment maintenance
verify_test_env()   : Verify environment setup

Documentation:
------------
Environment documentation available at ${_test_base}/README.md

Next Steps:
---------
1. Review the environment documentation
2. Source your shell configuration: source ~/.zshrc
3. Run verify_test_env() to ensure proper setup
4. Execute your first test suite with run-tests

EOL
}

#!/bin/zsh

configure_ssh() {
    local _username="$1"
    local _ssh_port="${2:-22}"

    log_info "Initializing enhanced SSH security configuration for FreeBSD"

    # Define all configuration paths with clear purpose
    local _paths=(
        SSH_CONFIG="/etc/ssh/sshd_config"              # Main SSH daemon configuration
        SSH_DIR="/etc/ssh"                             # SSH configuration directory
        EMPTY_DIR="/var/empty/sshd"                    # Chroot directory for SSH
        MODULI_FILE="/etc/ssh/moduli"                  # DH parameters file
        MONITOR_DIR="/var/log/ssh-monitor"             # SSH monitoring logs
        KEYS_DIR="/etc/ssh/keys"                       # SSH key storage
        BACKUP_DIR="/var/backups/ssh"                  # Configuration backups
    )

    # Create associative array for paths
    local -A PATHS
    for _path_def in "${_paths[@]}"; do
        local _key="${_path_def%%=*}"
        local _value="${_path_def#*=}"
        PATHS[$_key]="$_value"
    done

    # Validate environment and prerequisites
    if ! validate_ssh_environment "$_username" "${PATHS[@]}"; then
        return 1
    }

    # Define security parameters
    local -A SECURITY_PARAMS=(
        [MAX_AUTH_TRIES]=3                     # Maximum authentication attempts
        [LOGIN_GRACE_TIME]=30                  # Login grace period in seconds
        [CLIENT_ALIVE_INTERVAL]=300            # Client keepalive interval
        [CLIENT_ALIVE_COUNT_MAX]=2             # Maximum missed keepalive messages
        [MAX_STARTUPS]="10:30:100"            # Max concurrent unauthenticated connections
        [KEY_RETENTION_DAYS]=365               # Host key rotation period
        [MODULI_RETENTION_DAYS]=30             # DH parameters rotation period
        [LOG_RETENTION_DAYS]=30                # Log file retention period
    )

    # Create temporary working directory with proper security
    local _temp_dir
    _temp_dir=$(mktemp -d -t ssh-setup.XXXXXX) || {
        log_error "Failed to create temporary directory"
        return 1
    }

    # Ensure temporary directory cleanup
    trap 'rm -rf "$_temp_dir"' EXIT

    # Execute configuration steps with proper error handling
    local _steps=(
        "backup_existing_configuration"
        "generate_host_keys"
        "generate_moduli"
        "configure_sshd"
        "setup_monitoring"
        "configure_security_policies"
        "verify_configuration"
    )

    local _failed=0
    for _step in "${_steps[@]}"; do
        log_info "Executing SSH configuration step: $_step"
        if ! "$_step" "$_username" "$_ssh_port" "${PATHS[@]}" "$_temp_dir" "${SECURITY_PARAMS[@]}"; then
            log_error "Failed during $_step"
            _failed=$((_failed + 1))

            # Critical steps that should abort on failure
            case "$_step" in
                "backup_existing_configuration"|"configure_sshd"|"verify_configuration")
                    return 1
                    ;;
            esac
        fi
    done

    # Verify final configuration
    if ! verify_ssh_security "${PATHS[@]}" "${SECURITY_PARAMS[@]}"; then
        log_error "SSH security verification failed"
        return 1
    }

    # Only restart if everything is properly configured
    if ! restart_ssh_service; then
        log_error "Failed to restart SSH service safely"
        return 1
    }

    print_ssh_security_summary "$_username" "$_ssh_port" "${PATHS[@]}"
    return $((_failed > 0))

    # After restarting SSH, verify its state
    if ! verify_service_state "sshd" "$_ssh_port"; then
        log_error "SSH service failed to initialize properly"
        # Attempt to diagnose the issue
        {
            echo "SSH Service Failure Report"
            echo "======================="
            echo "Date: $(date)"
            echo "Configuration Test Output:"
            sshd -t
            echo "Process Status:"
            ps aux | grep sshd
            echo "Port Status:"
            sockstat -l | grep sshd
            echo "Auth Log Tail:"
            tail -n 50 /var/log/auth.log
        } > "/var/log/ssh/startup_failure_$(date +%Y%m%d_%H%M%S).log"
        return 1
    fi
}

validate_ssh_environment() {
    local _username="$1"
    shift
    local -A _paths=("$@")

    # Verify root privileges
    if [[ $(id -u) -ne 0 ]]; then
        log_error "SSH configuration requires root privileges"
        return 1
    }

    # Validate username
    if ! pw user show "$_username" >/dev/null 2>&1; then
        log_error "User $_username does not exist"
        return 1
    }

    # Check for required commands
    local _required_commands=(
        "ssh-keygen"
        "sshd"
        "openssl"
        "pw"
        "procstat"
    )

    local _missing_commands=()
    for _cmd in "${_required_commands[@]}"; do
        if ! command -v "$_cmd" >/dev/null 2>&1; then
            _missing_commands+=("$_cmd")
        fi
    done

    if [[ ${#_missing_commands[@]} -gt 0 ]]; then
        log_error "Missing required commands: ${_missing_commands[*]}"
        return 1
    }

    # Create required directories with secure permissions
    for _dir in "${_paths[@]}"; do
        if ! mkdir -p "$_dir" 2>/dev/null; then
            log_error "Failed to create directory: $_dir"
            return 1
        fi
        chmod 755 "$_dir"
    done

    # The empty directory should be more restrictive
    chmod 711 "${_paths[EMPTY_DIR]}"

    return 0
}

backup_existing_configuration() {
    local _username="$1"
    shift
    local -A _paths=("$@")

    local _timestamp=$(date +%Y%m%d_%H%M%S)
    local _backup_dir="${_paths[BACKUP_DIR]}"
    local _backup_file="${_backup_dir}/${BACKUP_PREFIX}_${_timestamp}.tar.gz"

    # Create backup directory with secure permissions
    if ! mkdir -p "$_backup_dir" 2>/dev/null; then
        log_error "Failed to create backup directory: $_backup_dir"
        return 1
    fi
    chmod 700 "$_backup_dir"

    # Create the backup
    tar czf "$_backup_file" -C / etc/ssh sysctl.conf 2>/dev/null

    # Create backup manifest
    {
        echo "System Configuration Backup"
        echo "Generated: $(date)"
        echo "System: $(uname -a)"
        echo "User: $_username"
        echo
        echo "Files:"
        tar tzf "$_backup_file" | sed 's/^/- /'
    } > "${_backup_file}.manifest"

    # Rotate old backups
    rotate_backups "$_backup_dir" "$BACKUP_RETENTION" "$BACKUP_PREFIX"

    log_info "Created system configuration backup: $_backup_file"
    return 0
}

generate_host_keys() {
    local _username="$1"
    shift
    local -A _paths=("$@")

    # Define key specifications
    local -A _key_specs=(
        [ed25519]="256"
        [rsa]="4096"
        [ecdsa]="384"
    )

    local _failed=0
    for _key_type in "${!_key_specs[@]}"; do
        local _key_file="${_paths[SSH_DIR]}/ssh_host_${_key_type}_key"
        local _key_size="${_key_specs[$_key_type]}"

        # Check if key needs regeneration
        if [[ ! -f "$_key_file" ]] || \
           [[ $(stat -f %m "$_key_file") -lt $(date -v-365d +%s) ]]; then

            log_info "Generating new $_key_type host key..."

            # Remove old keys safely
            shred -u "$_key_file" "${_key_file}.pub" 2>/dev/null || true

            # Generate new key with proper size
            if ! ssh-keygen -t "$_key_type" \
                          -b "$_key_size" \
                          -f "$_key_file" \
                          -N "" \
                          -C "$(hostname) ${_key_type} host key" \
                          -q; then
                log_error "Failed to generate $_key_type host key"
                _failed=$((_failed + 1))
                continue
            fi

            # Set secure permissions
            chmod 600 "$_key_file"
            chmod 644 "${_key_file}.pub"

            # Calculate and store key fingerprints
            local _fingerprint
            _fingerprint=$(ssh-keygen -lf "$_key_file")
            echo "$_fingerprint" >> "${_paths[SSH_DIR]}/host_keys_fingerprints"
        fi
    done

    return $((_failed > 0))
}

generate_moduli() {
    local _username="$1"
    shift
    local -A _paths=("$@")

    # Check if moduli file needs regeneration
    if [[ ! -f "${_paths[MODULI_FILE]}" ]] || \
       [[ $(stat -f %m "${_paths[MODULI_FILE]}") -lt $(date -v-30d +%s) ]]; then

        log_info "Generating new DH moduli (this may take a while)..."

        local _tmp_moduli
        _tmp_moduli=$(mktemp) || {
            log_error "Failed to create temporary file for moduli generation"
            return 1
        }

        # Generate strong DH parameters
        if ! ssh-keygen -M generate \
                      -O bits=4096 \
                      -O memory=512 \
                      -O parallel=4 \
                      -o "$_tmp_moduli"; then
            log_error "Failed to generate DH moduli"
            rm -f "$_tmp_moduli"
            return 1
        fi

        # Screen the generated moduli for security
        if ! ssh-keygen -M screen \
                      -f "$_tmp_moduli" \
                      -o "${_paths[MODULI_FILE]}"; then
            log_error "Failed to screen DH moduli"
            rm -f "$_tmp_moduli"
            return 1
        fi

        rm -f "$_tmp_moduli"
        chmod 644 "${_paths[MODULI_FILE]}"
    fi

    return 0
}

configure_sshd() {
    local _username="$1"
    local _ssh_port="$2"
    shift 2
    local -A _paths=("$@")

    local _temp_config="${_paths[SSH_DIR]}/sshd_config.new"

    # Create new SSH configuration with security best practices
    cat > "$_temp_config" << EOF
# SSH Daemon Configuration for FreeBSD
# Generated: $(date)
# System: $(hostname)

# Security and authentication settings
Protocol 2
Port $_ssh_port

# Host keys (ordered by preference)
HostKey ${_paths[SSH_DIR]}/ssh_host_ed25519_key
HostKey ${_paths[SSH_DIR]}/ssh_host_rsa_key
HostKey ${_paths[SSH_DIR]}/ssh_host_ecdsa_key

# Authentication settings
PubkeyAuthentication yes
PasswordAuthentication no
PermitRootLogin no
MaxAuthTries ${SECURITY_PARAMS[MAX_AUTH_TRIES]}
AuthenticationMethods publickey

# Access control
AllowUsers $_username
AllowGroups wheel

# Network settings
AddressFamily inet
ListenAddress 0.0.0.0
LoginGraceTime ${SECURITY_PARAMS[LOGIN_GRACE_TIME]}
MaxStartups ${SECURITY_PARAMS[MAX_STARTUPS]}
TCPKeepAlive yes
ClientAliveInterval ${SECURITY_PARAMS[CLIENT_ALIVE_INTERVAL]}
ClientAliveCountMax ${SECURITY_PARAMS[CLIENT_ALIVE_COUNT_MAX]}

# Cryptographic settings
Ciphers chacha20-poly1305@openssh.com,aes256-gcm@openssh.com,aes128-gcm@openssh.com
MACs hmac-sha2-512-etm@openssh.com,hmac-sha2-256-etm@openssh.com
KexAlgorithms curve25519-sha256@libssh.org,diffie-hellman-group16-sha512,diffie-hellman-group18-sha512

# Security features
UsePAM yes
Compression no
X11Forwarding no
AllowTcpForwarding no
PermitTunnel no
PermitUserEnvironment no
StrictModes yes
UsePrivilegeSeparation sandbox
ChrootDirectory none
PrintMotd no

# Logging
SyslogFacility AUTH
LogLevel VERBOSE

# Rate limiting
MaxStartups 10:30:60

# Environment
AcceptEnv LANG LC_*

# Additional security measures
AllowAgentForwarding no
AllowStreamLocalForwarding no
AuthenticationMethods publickey
KexAlgorithms curve25519-sha256@libssh.org,diffie-hellman-group16-sha512
EOF

    # Validate the new configuration
    if ! sshd -t -f "$_temp_config"; then
        log_error "SSH configuration validation failed"
        return 1
    }

    # Install the new configuration
    if ! mv "$_temp_config" "${_paths[SSH_CONFIG]}"; then
        log_error "Failed to install new SSH configuration"
        return 1
    }

    if ! sshd -t -f "$_temp_config"; then
    log_error "SSH configuration validation failed"
    rm -f "$_temp_config"  # Clean up temporary file
    return 1
fi

    chmod 600 "${_paths[SSH_CONFIG]}"
    return 0
}

setup_monitoring() {
    local _username="$1"
    shift
    local -A _paths=("$@")

    # Create monitoring script
    local _monitor_script="${_paths[SSH_DIR]}/scripts/ssh-monitor"
    mkdir -p "$(dirname $_monitor_script)"

    cat > "$_monitor_script" << 'EOF'
#!/bin/sh
# Enhanced SSH Connection Monitor and Security Analyzer

set -e
set -u

# Initialize monitoring
MONITOR_DIR="${_paths[MONITOR_DIR]}"
mkdir -p "$MONITOR_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Monitor active connections
{
    echo "=== SSH Connection Report ==="
    echo "Generated: $(date)"
    echo

    echo "Active Connections:"
    sockstat -4l | grep sshd

    echo
    echo "Connection Details:"
    netstat -an | grep ":22 " | sort
} > "${MONITOR_DIR}/connections_${TIMESTAMP}.log"

# Analyze authentication attempts
{
    echo "=== SSH Authentication Analysis ==="
    echo "Generated: $(date)"
    echo

    # Failed authentication attempts
    echo "Failed Authentication Attempts (Last 24 Hours):"
    grep "Failed password" /var/log/auth.log | \
        awk '{print $1,$2,$3,$11}' | \
        sort | uniq -c | sort -nr

    echo
    echo "Authentication Method Statistics:"
    grep "Accepted" /var/log/auth.log | \
        awk '{print $1,$2,$3,$7}' | \
        sort | uniq -c | sort -nr
} > "${MONITOR_DIR}/auth_${TIMESTAMP}.log"

# Analyze potential attacks
{
    echo "=== SSH Security Analysis ==="
    echo "Generated: $(date)"
    echo

    # Count rapid connection attempts
    echo "Rapid Connection Analysis:"
    {
        # Analyze authentication attempts within short time windows
        grep "sshd" /var/log/auth.log | \
        awk '{print $1" "$2" "$3}' | \
        sort | uniq -c | \
        awk '$1 >= 10 {print "  - " $1 " attempts at " $2" "$3" "$4}'
    }

    echo
    echo "Source IP Analysis:"
    {
        # Identify and categorize source IPs by behavior pattern
        grep "sshd" /var/log/auth.log | \
        awk '{print $11}' | grep -E "^[0-9]" | \
        sort | uniq -c | sort -nr | \
        while read count ip; do
            if [ "$count" -gt 100 ]; then
                echo "  - High Activity ($count attempts): $ip"
                # Look up IP information if geoip is available
                if command -v geoiplookup >/dev/null 2>&1; then
                    geoiplookup "$ip" | sed 's/^/    /'
                fi
            fi
        done
    }

    echo
    echo "Username Analysis:"
    {
        # Analyze attempted usernames to identify attack patterns
        grep "Failed password" /var/log/auth.log | \
        awk '{print $9}' | sort | uniq -c | sort -nr | \
        while read count username; do
            if [ "$count" -gt 10 ]; then
                echo "  - Attempted Username ($count times): $username"
            fi
        done
    }

    echo
    echo "Attack Pattern Analysis:"
    {
        # Look for known attack patterns
        PATTERNS=(
            "root login refused"
            "invalid user"
            "Bad protocol version"
            "Could not negotiate a key exchange algorithm"
            "Unable to negotiate with"
            "error: maximum authentication attempts exceeded"
        )

        for pattern in "${PATTERNS[@]}"; do
            count=$(grep -c "$pattern" /var/log/auth.log || true)
            if [ "$count" -gt 0 ]; then
                echo "  - $pattern: $count occurrences"
            fi
        done
    }

    echo
    echo "Connection Distribution:"
    {
        # Analyze connection patterns over time
        echo "  Hourly connection attempts (last 24 hours):"
        for hour in $(seq -w 0 23); do
            count=$(grep "sshd" /var/log/auth.log | grep "$(date +%Y-%m-%d)" | grep ":$hour:" | wc -l)
            printf "    %02d:00-%02d:59: %5d connections\n" "$hour" "$hour" "$count"
        done
    }
} > "${MONITOR_DIR}/security_${TIMESTAMP}.log"

# Generate threat intelligence report
{
    echo "=== SSH Threat Intelligence Report ==="
    echo "Generated: $(date)"
    echo

    # Identify and classify potential threats
    echo "Threat Classification:"
    {
        # Define threat levels and their thresholds
        declare -A THREAT_LEVELS=(
            [CRITICAL]=100
            [HIGH]=50
            [MEDIUM]=20
            [LOW]=5
        )

        # Analyze and classify threats based on activity patterns
        for ip in $(grep "sshd" /var/log/auth.log | awk '{print $11}' | grep -E "^[0-9]" | sort | uniq); do
            count=$(grep "$ip" /var/log/auth.log | wc -l)
            failed=$(grep "Failed password" /var/log/auth.log | grep "$ip" | wc -l)

            # Calculate threat score based on various factors
            threat_score=$((count + failed * 2))

            # Classify threat level
            if [ "$threat_score" -ge "${THREAT_LEVELS[CRITICAL]}" ]; then
                echo "  CRITICAL: IP $ip (Score: $threat_score)"
                echo "    - Total Attempts: $count"
                echo "    - Failed Attempts: $failed"
                if command -v geoiplookup >/dev/null 2>&1; then
                    geoiplookup "$ip" | sed 's/^/    /'
                fi
            elif [ "$threat_score" -ge "${THREAT_LEVELS[HIGH]}" ]; then
                echo "  HIGH: IP $ip (Score: $threat_score)"
            fi
        done
    }

    echo
    echo "Recommended Actions:"
    {
        # Generate action recommendations based on threat analysis
        high_risk_ips=$(grep "sshd" /var/log/auth.log | \
                       awk '{print $11}' | grep -E "^[0-9]" | \
                       sort | uniq -c | sort -nr | \
                       awk '$1 >= 50 {print $2}')

        if [ -n "$high_risk_ips" ]; then
            echo "  Consider blocking the following high-risk IPs:"
            echo "$high_risk_ips" | sed 's/^/    /'

            # Generate ipfw rules for identified threats
            echo
            echo "  Sample ipfw rules:"
            echo "$high_risk_ips" | \
                awk '{print "    ipfw add deny ip from " $1 " to me 22"}'
        fi

        # Check for configuration vulnerabilities
        echo
        echo "  Configuration Recommendations:"
        sshd -T | while read -r line; do
            case "$line" in
                "passwordauthentication yes")
                    echo "    - Disable password authentication"
                    ;;
                "permitrootlogin yes")
                    echo "    - Disable root login"
                    ;;
                "x11forwarding yes")
                    echo "    - Disable X11 forwarding"
                    ;;
            esac
        done
    }
} > "${MONITOR_DIR}/threats_${TIMESTAMP}.log"

# Generate consolidated report
{
    echo "=== SSH Security Status Summary ==="
    echo "Generated: $(date)"
    echo "System: $(hostname)"
    echo

    # Include key metrics
    echo "Key Metrics:"
    echo "  - Total Connections: $(grep "sshd" /var/log/auth.log | wc -l)"
    echo "  - Failed Attempts: $(grep "Failed password" /var/log/auth.log | wc -l)"
    echo "  - Unique IPs: $(grep "sshd" /var/log/auth.log | awk '{print $11}' | grep -E "^[0-9]" | sort | uniq | wc -l)"
    echo "  - Authentication Failures: $(grep "Authentication failure" /var/log/auth.log | wc -l)"

    # Include recent activity
    echo
    echo "Recent Activity (Last Hour):"
    {
        start_time=$(date -v-1H +%s)
        while read -r line; do
            timestamp=$(date -j -f "%b %d %H:%M:%S" "$(echo "$line" | awk '{print $1,$2,$3}')" +%s 2>/dev/null)
            if [ "$timestamp" -ge "$start_time" ]; then
                echo "  - $line"
            fi
        done < <(tail -1000 /var/log/auth.log | grep "sshd")
    }

    # Include current connections
    echo
    echo "Current Connections:"
    sockstat -4l | grep sshd | sed 's/^/  /'

    # Include top offenders
    echo
    echo "Top Offenders (Last 24 Hours):"
    grep "sshd" /var/log/auth.log | \
        awk '{print $11}' | grep -E "^[0-9]" | \
        sort | uniq -c | sort -nr | head -5 | \
        while read -r count ip; do
            echo "  - $ip ($count attempts)"
        done

} > "${MONITOR_DIR}/summary_${TIMESTAMP}.log"

# Clean up old logs
find "$MONITOR_DIR" -type f -mtime +${RETENTION_DAYS} -delete

# Check if we need to send alerts
if grep -q "CRITICAL" "${MONITOR_DIR}/threats_${TIMESTAMP}.log"; then
    echo "CRITICAL SSH security threats detected!" | \
        mail -s "SSH Security Alert - $(hostname)" root
fi
EOF

    # Set appropriate permissions
    chmod 700 "$_monitor_script"
    chown root:wheel "$_monitor_script"

    # Create cron job for monitoring
    local _cron_file="/etc/cron.d/ssh-monitor"
    cat > "$_cron_file" << EOF
# SSH Security Monitoring
SHELL=/bin/sh
PATH=/sbin:/bin:/usr/sbin:/usr/bin:/usr/local/sbin:/usr/local/bin
MAILTO=root

# Run monitoring every 15 minutes
*/15 * * * * root $_monitor_script

# Generate daily summary at midnight
0 0 * * * root $_monitor_script daily
EOF

    chmod 644 "$_cron_file"

    return 0
}

# The rest of the functions (configure_security_policies, verify_configuration, etc.)
# would follow the same pattern of comprehensive implementation with proper error
# handling and logging. Would you like me to continue with those functions?

#!/bin/zsh

# FreeBSD Development Environment Configuration
# This module establishes a comprehensive development environment optimized for
# systems programming, kernel development, and general software development.

setup_development() {
    local _username="$1"
    local _dev_base="${2:-/home/${_username}/development}"

    log_info "Initializing comprehensive FreeBSD development environment"

    # Configuration paths structure - defines all key directories and files
    local _paths=(
        DEV_BASE="${_dev_base}"                            # Base development directory
        TOOLCHAINS_DIR="${_dev_base}/toolchains"          # Compiler configurations
        ENVIRONMENTS_DIR="${_dev_base}/environments"       # Language environments
        SCRIPTS_DIR="${_dev_base}/scripts"                # Development scripts
        TEMPLATES_DIR="${_dev_base}/templates"            # Project templates
        TOOLS_DIR="${_dev_base}/tools"                    # Development tools
        CONFIG_DIR="${_dev_base}/configs"                 # Tool configurations
        BACKUP_DIR="${_dev_base}/backups"                 # Environment backups
        CACHE_DIR="/home/${_username}/.cache/dev"         # Cache storage
    )

    # Create paths associative array
    local -A PATHS
    for _path_def in "${_paths[@]}"; do
        local _key="${_path_def%%=*}"
        local _value="${_path_def#*=}"
        PATHS[$_key]="$_value"
    done

    # Define supported development environments
    local -A DEV_ENVIRONMENTS=(
        [cpp]="gcc clang"
        [python]="python3 pip venv"
        [rust]="cargo rustc"
        [go]="go"
        [nodejs]="node npm"
        [java]="openjdk maven"
    )

    # Define required development tools
    local -A DEV_TOOLS=(
        [version_control]="git git-lfs"
        [build_tools]="cmake ninja ccache"
        [debugging]="gdb lldb strace truss"
        [analysis]="cppcheck valgrind"
        [code_navigation]="ctags cscope global"
        [documentation]="doxygen graphviz"
        [editors]="vim neovim"
    )

    # Validate environment and prerequisites
    if ! validate_development_environment "$_username" "${PATHS[@]}" "${DEV_ENVIRONMENTS[@]}" "${DEV_TOOLS[@]}"; then
        return 1
    }

    # Create a secure temporary directory for setup
    local _temp_dir
    _temp_dir=$(mktemp -d -t dev-setup.XXXXXX) || {
        log_error "Failed to create temporary directory"
        return 1
    }

    # Ensure temporary directory cleanup
    trap 'rm -rf "$_temp_dir"' EXIT

    # Configuration steps
    local _steps=(
        "create_directory_structure"
        "configure_toolchains"
        "setup_language_environments"
        "configure_development_tools"
        "setup_project_templates"
        "configure_version_control"
        "setup_editor_configuration"
        "configure_debugging_tools"
        "setup_documentation"
        "configure_user_environment"
    )

    # Execute configuration steps with proper error handling
    local _failed=0
    for _step in "${_steps[@]}"; do
        log_info "Executing development setup step: $_step"
        if ! "$_step" "$_username" "${PATHS[@]}" "$_temp_dir"; then
            log_error "Failed during $_step"
            _failed=$((_failed + 1))
            # Critical steps that should abort on failure
            case "$_step" in
                "create_directory_structure"|"configure_toolchains")
                    return 1
                    ;;
            esac
        fi
    done

    # Verify the setup
    if ! verify_development_setup "${PATHS[@]}"; then
        log_error "Development environment verification failed"
        return 1
    }

    print_development_summary "${PATHS[@]}"
    return $((_failed > 0))
}

validate_development_environment() {
    local _username="$1"
    shift
    local -A _paths=("$@")

    # Verify user exists and has proper permissions
    if ! pw user show "$_username" >/dev/null 2>&1; then
        log_error "User $_username does not exist"
        return 1
    fi

    # Check for required commands
    local _missing_commands=()

    # Core development tools
    local _required_commands=(
        "cc"            # Base C compiler
        "c++"          # Base C++ compiler
        "make"         # Basic build tool
        "ld"           # Linker
        "ar"           # Archive manager
        "pkg"          # Package manager
        "git"          # Version control
    )

    for _cmd in "${_required_commands[@]}"; do
        if ! command -v "$_cmd" >/dev/null 2>&1; then
            _missing_commands+=("$_cmd")
        fi
    done

    if [[ ${#_missing_commands[@]} -gt 0 ]]; then
        log_error "Missing required commands: ${_missing_commands[*]}"
        log_info "Install missing tools using: pkg install -y ${_missing_commands[*]}"
        return 1
    }

    # Check available disk space (minimum 10GB)
    local _available_space
    _available_space=$(df -k "${_paths[DEV_BASE]%/*}" | awk 'NR==2 {print $4}')
    if [[ "${_available_space:-0}" -lt 10485760 ]]; then
        log_error "Insufficient disk space. Required: 10GB, Available: $((_available_space / 1024 / 1024))GB"
        return 1
    }

    return 0
}

create_directory_structure() {
    local _username="$1"
    shift
    local -A _paths=("$@")

    # Define directory structure with permissions
    local -A _directories=(
        [toolchains]="750:Compiler and toolchain configurations"
        [environments]="750:Language-specific environments"
        [scripts]="755:Development utility scripts"
        [templates]="750:Project templates and boilerplates"
        [tools]="755:Development tools and utilities"
        [configs]="750:Tool configurations"
        [backups]="750:Environment backups"
        [projects]="755:Development projects"
        [docs]="755:Documentation"
    )

    # Create each directory with proper permissions and documentation
    for _dir in "${!_directories[@]}"; do
        local _mode="${_directories[$_dir]%%:*}"
        local _desc="${_directories[$_dir]#*:}"
        local _path="${_paths[DEV_BASE]}/${_dir}"

        if ! mkdir -p "$_path" 2>/dev/null; then
            log_error "Failed to create directory: $_path"
            return 1
        fi

        chmod "$_mode" "$_path"
        chown "${_username}:wheel" "$_path"

        # Create README in each directory
        cat > "${_path}/README.md" << EOF
# ${_dir^} Directory

${_desc}

## Purpose

This directory is part of the FreeBSD development environment structure.
Created: $(date)
Permission Mode: ${_mode}

## Contents

EOF
    done

    return 0
}

configure_toolchains() {
    local _username="$1"
    shift
    local -A _paths=("$@")
    local _temp_dir="$3"

    # Configure GCC toolchain
    cat > "${_temp_dir}/gcc.conf" << 'EOF'
# GCC Toolchain Configuration for FreeBSD Development
# This configuration optimizes for development with debugging capabilities

# Basic optimization settings
CFLAGS="-O2 -pipe -fstack-protector-strong"

# Architecture-specific optimizations
if [ "$(uname -m)" = "amd64" ]; then
    CFLAGS="$CFLAGS -march=native -mtune=native"
fi

# Development and debugging flags
CFLAGS="$CFLAGS -g -fno-omit-frame-pointer"

# Security enhancements
CFLAGS="$CFLAGS -D_FORTIFY_SOURCE=2 -fPIE"

# Warning flags for development
CFLAGS="$CFLAGS -Wall -Wextra -Wpedantic -Wformat-security"

# C++ specific flags
CXXFLAGS="$CFLAGS -std=c++17 -fno-rtti"

# Linker flags
LDFLAGS="-Wl,-z,relro -Wl,-z,now -pie"

# Make settings
MAKEFLAGS="-j$(sysctl -n hw.ncpu)"

# Environment exports
export CFLAGS CXXFLAGS LDFLAGS MAKEFLAGS

# ccache configuration
if command -v ccache >/dev/null 2>&1; then
    export CC="ccache gcc"
    export CXX="ccache g++"
fi

# Build type detection
detect_build_type() {
    if [ -f CMakeLists.txt ]; then
        echo "cmake"
    elif [ -f configure ]; then
        echo "autotools"
    elif [ -f Makefile ]; then
        echo "make"
    else
        echo "unknown"
    fi
}

# Build wrapper function
build() {
    local build_type=$(detect_build_type)

    case "$build_type" in
        cmake)
            cmake -B build -DCMAKE_BUILD_TYPE=Debug \
                         -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
                         -DCMAKE_C_FLAGS="$CFLAGS" \
                         -DCMAKE_CXX_FLAGS="$CXXFLAGS" \
                         -DCMAKE_EXE_LINKER_FLAGS="$LDFLAGS" && \
            cmake --build build -j$(sysctl -n hw.ncpu)
            ;;
        autotools)
            ./configure CFLAGS="$CFLAGS" CXXFLAGS="$CXXFLAGS" LDFLAGS="$LDFLAGS" && \
            make -j$(sysctl -n hw.ncpu)
            ;;
        make)
            make -j$(sysctl -n hw.ncpu)
            ;;
        *)
            echo "Unknown build system"
            return 1
            ;;
    esac
}

# Development environment helpers
create_compilation_database() {
    if [ -f CMakeLists.txt ]; then
        cmake -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
        ln -sf build/compile_commands.json .
    elif [ -f Makefile ]; then
        bear -- make
    fi
}

setup_debug_helpers() {
    if [ ! -d .debug ]; then
        mkdir .debug
        cat > .debug/gdbinit << 'GDBINIT'
set print pretty on
set print object on
set print static-members on
set print vtbl on
set print demangle on
GDBINIT
    fi
}
EOF

    # Configure Clang toolchain
    cat > "${_temp_dir}/clang.conf" << 'EOF'
# Clang Toolchain Configuration for FreeBSD Development
# This configuration optimizes for development with advanced sanitization

# Basic optimization settings
CFLAGS="-O2 -pipe"

# Architecture-specific optimizations
if [ "$(uname -m)" = "amd64" ]; then
    CFLAGS="$CFLAGS -march=native -mtune=native"
fi

# Development and debugging flags
CFLAGS="$CFLAGS -g -fno-omit-frame-pointer"

# Security enhancements
CFLAGS="$CFLAGS -D_FORTIFY_SOURCE=2 -fPIE -fstack-protector-strong"

# Sanitizer support
CFLAGS="$CFLAGS -fsanitize=address,undefined"

# Warning flags
CFLAGS="$CFLAGS -Weverything -Wno-padded -Wno-disabled-macro-expansion"

# C++ specific flags
CXXFLAGS="$CFLAGS -std=c++17 -stdlib=libc++"

# Linker flags
LDFLAGS="-Wl,-z,relro -Wl,-z,now -pie -fsanitize=address,undefined"

# Make settings
MAKEFLAGS="-j$(sysctl -n hw.ncpu)"

# Environment exports
export CFLAGS CXXFLAGS LDFLAGS MAKEFLAGS

# ccache configuration
if command -v ccache >/dev/null 2>&1; then
    export CC="ccache clang"
    export CXX="ccache clang++"
fi

# LLVM tool integration
export PATH="/usr/local/llvm/bin:$PATH"

# Build type detection and wrapper functions
detect_build_type() {
    if [ -f CMakeLists.txt ]; then
        echo "cmake"
    elif [ -f configure ]; then
        echo "autotools"
    elif [ -f Makefile ]; then
        echo "make"
    else
        echo "unknown"
    fi
}

build() {
    local build_type=$(detect_build_type)

    case "$build_type" in
        cmake)
            cmake -B build -DCMAKE_BUILD_TYPE=Debug \
                         -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
                         -DCMAKE_C_FLAGS="$CFLAGS" \
                         -DCMAKE_CXX_FLAGS="$CXXFLAGS" \
                         -DCMAKE_EXE_LINKER_FLAGS="$LDFLAGS" \
                         -DCMAKE_C_COMPILER=clang \
                         -DCMAKE_CXX_COMPILER=clang++ && \
            cmake --build build -j$(sysctl -n hw.ncpu)
            ;;
        autotools)
            ./configure CC=clang CXX=clang++ \
                      CFLAGS="$CFLAGS" CXXFLAGS="$CXXFLAGS" LDFLAGS="$LDFLAGS" && \
            make -j$(sysctl -n hw.ncpu)
            ;;
        make)
            make -j$(sysctl -n hw.ncpu) \
                CC=clang CXX=clang++ \
                CFLAGS="$CFLAGS" CXXFLAGS="$CXXFLAGS" LDFLAGS="$LDFLAGS"
            ;;
        *)
            echo "Unknown build system"
            return 1
            ;;
    esac
}

# Development environment helpers
setup_sanitizers() {
    export ASAN_OPTIONS=detect_stack_use_after_return=1:check_initialization_order=1
    export UBSAN_OPTIONS=print_stacktrace=1
    export LSAN_OPTIONS=verbosity=1:log_threads=1
}

create_compilation_database() {
    if [ -f CMakeLists.txt ]; then
        cmake -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
        ln -sf build/compile_commands.json .
    else
        intercept-build make
    fi
}

setup_debug_helpers() {
    if [ ! -d .debug ]; then
        mkdir .debug
        cat > .debug/lldbinit << 'LLDBINIT'
# LLDB Configuration for Development
# Enable source line numbers and function names
settings set target.load-script-from-symbol-file true
settings set target.inline-breakpoint-strategy always

# Configure source code display
settings set target.source-map /builddir /workspace
settings set target.max-zero-distance-count 3

# Memory inspection settings
settings set target.max-memory-read-size 1024
settings set target.max-string-summary-length 1024

# Thread and stack frame display
settings set thread-format "thread: #{thread.index}\t#{thread.id}\t#{thread.stop-reason}\t#{thread.queue}"
settings set frame-format "frame #${frame.index}: ${frame.pc}{ ${module.file.basename}`${function.name-with-args}{${function.pc-offset}}}{ at ${line.file.basename}:${line.number}}\n"

# Data formatting
settings set target.max-children-count 100
settings set target.prefer-dynamic-value run-target

# Breakpoint settings
settings set target.process.thread.step-avoid-regexp ""
settings set target.process.thread.step-in-avoid-regexp ""

# Python script integration for custom debugging
command script import ~/.debug/lldb_scripts.py
LLDBINIT

        cat > .debug/lldb_scripts.py << 'LLDBSCRIPT'
import lldb
import os

def __lldb_init_module(debugger, internal_dict):
    """Initialize custom LLDB commands and settings."""
    debugger.HandleCommand('command script add -f lldb_scripts.print_memory pm')
    debugger.HandleCommand('command script add -f lldb_scripts.trace_calls tc')

def print_memory(debugger, command, result, internal_dict):
    """Custom memory inspection command with enhanced formatting."""
    target = debugger.GetSelectedTarget()
    process = target.GetProcess()
    thread = process.GetSelectedThread()
    frame = thread.GetSelectedFrame()

    # Parse address and size from command
    args = command.split()
    if len(args) != 2:
        print("Usage: pm <address> <size>", file=result)
        return

    try:
        addr = int(args[0], 0)
        size = int(args[1])
    except ValueError:
        print("Invalid address or size", file=result)
        return

    error = lldb.SBError()
    memory = process.ReadMemory(addr, size, error)
    if error.Success():
        # Format memory display with both hex and ASCII representation
        for i in range(0, len(memory), 16):
            chunk = memory[i:i+16]
            hex_dump = ' '.join(['{:02x}'.format(b) for b in chunk])
            ascii_dump = ''.join([chr(b) if 32 <= b <= 126 else '.' for b in chunk])
            print("{:08x}  {:48s}  |{:16s}|".format(addr + i, hex_dump, ascii_dump), file=result)
    else:
        print("Error reading memory: {}".format(error.GetCString()), file=result)

def trace_calls(debugger, command, result, internal_dict):
    """Set up function call tracing with customizable filters."""
    target = debugger.GetSelectedTarget()

    # Set breakpoints on function entries
    for module in target.module_iter():
        for symbol in module:
            if symbol.GetType() == lldb.eSymbolTypeCode:
                bp = target.BreakpointCreateByName(symbol.GetName())
                bp.SetScriptCallbackFunction("lldb_scripts.trace_callback")

def trace_callback(frame, bp_loc, internal_dict):
    """Callback for function call tracing."""
    thread = frame.GetThread()
    function = frame.GetFunction()

    # Format the call trace with arguments
    args = []
    for i in range(frame.GetNumArguments()):
        arg = frame.GetArgument(i)
        args.append("{}={}".format(arg.GetName(), arg.GetValue()))

    print("-> {} ({})".format(function.GetName(), ', '.join(args)))
    return False  # Continue execution
LLDBSCRIPT
    fi

    # Set up debugging shortcuts and utilities
    cat > .debug/debug_helpers.sh << 'DEBUGHELP'
#!/bin/sh
# Debugging Helper Functions for Development

# Enhanced core dump analysis
analyze_core() {
    local core_file="$1"
    local binary="$2"

    if [ ! -f "$core_file" ] || [ ! -f "$binary" ]; then
        echo "Usage: analyze_core <core-file> <binary>"
        return 1
    fi

    # Create analysis directory
    local analysis_dir="debug_analysis_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$analysis_dir"

    # Generate initial analysis report
    {
        echo "Core Dump Analysis Report"
        echo "======================="
        echo "Date: $(date)"
        echo "Core File: $core_file"
        echo "Binary: $binary"
        echo

        echo "System Information:"
        uname -a
        echo

        echo "Binary Information:"
        file "$binary"
        echo

        echo "Shared Library Dependencies:"
        ldd "$binary"
        echo

        echo "Stack Trace:"
        gdb -q -c "$core_file" "$binary" -ex "thread apply all bt full" -ex quit

        echo
        echo "Register State:"
        gdb -q -c "$core_file" "$binary" -ex "info registers" -ex quit

    } > "$analysis_dir/analysis_report.txt"

    # Create debug session script
    cat > "$analysis_dir/debug_session.gdb" << EOF
set pagination off
set logging on gdb_session.log
set print pretty on
set print object on
set print static-members on
set print demangle on

file $binary
core-file $core_file

echo \n--- Stack Trace ---\n
thread apply all bt full

echo \n--- Memory Information ---\n
info proc mappings

echo \n--- Register State ---\n
info registers

echo \n--- Local Variables ---\n
frame apply all info locals
EOF

    echo "Analysis completed. Results available in $analysis_dir/"
    echo "To start an interactive debug session:"
    echo "gdb -x $analysis_dir/debug_session.gdb"
}

# Memory leak detection wrapper
check_leaks() {
    local binary="$1"
    shift

    if [ ! -f "$binary" ]; then
        echo "Usage: check_leaks <binary> [args...]"
        return 1
    }

    # Set up Valgrind options for detailed leak detection
    local valgrind_opts="--leak-check=full \
                        --show-leak-kinds=all \
                        --track-origins=yes \
                        --verbose \
                        --log-file=valgrind_report.txt"

    # Run with Valgrind
    valgrind $valgrind_opts "$binary" "$@"

    # Analyze the report
    if [ -f valgrind_report.txt ]; then
        {
            echo "Memory Leak Analysis Summary"
            echo "=========================="
            echo
            grep -A 5 "LEAK SUMMARY" valgrind_report.txt
            echo
            echo "Detailed leak information available in valgrind_report.txt"
        } | tee leak_summary.txt
    fi
}

# Thread state analysis
analyze_threads() {
    local pid="$1"

    if [ -z "$pid" ]; then
        echo "Usage: analyze_threads <pid>"
        return 1
    }

    # Create thread analysis report
    {
        echo "Thread State Analysis"
        echo "===================="
        echo "Process ID: $pid"
        echo "Date: $(date)"
        echo

        echo "Process Information:"
        ps -o pid,ppid,user,%cpu,%mem,vsz,rss,state,start,time -p "$pid"
        echo

        echo "Thread List:"
        procstat -t "$pid"
        echo

        echo "Thread Stack Traces:"
        gdb -q -p "$pid" -ex "thread apply all bt" -ex quit

    } > "thread_analysis_${pid}.txt"

    echo "Thread analysis completed. Results available in thread_analysis_${pid}.txt"
}

# Performance profiling wrapper
profile_execution() {
    local binary="$1"
    shift

    if [ ! -f "$binary" ]; then
        echo "Usage: profile_execution <binary> [args...]"
        return 1
    }

    # Create profile directory
    local profile_dir="profile_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$profile_dir"

    # Run with perf
    perf record -g -o "$profile_dir/perf.data" "$binary" "$@"

    # Generate reports
    cd "$profile_dir" || return 1

    # CPU profiling report
    perf report -g 'graph,0.5,caller' > cpu_profile.txt

    # Generate flame graph if available
    if command -v flamegraph.pl >/dev/null 2>&1; then
        perf script | stackcollapse-perf.pl | flamegraph.pl > profile_flamegraph.svg
    fi

    echo "Profile analysis completed. Results available in $profile_dir/"
}

# Core pattern setup for debugging
setup_core_pattern() {
    if [ "$(id -u)" -ne 0 ]; then
        echo "This function requires root privileges"
        return 1
    }

    # Configure core dump pattern
    sysctl kern.corefile="/var/cores/%N.%P.%t.core"

    # Create cores directory with appropriate permissions
    mkdir -p /var/cores
    chmod 1777 /var/cores

    # Set core size limit
    sysctl kern.coredump=1
    sysctl kern.sugid_coredump=1

    echo "Core dump configuration completed. Cores will be saved in /var/cores/"
}
DEBUGHELP

    # Add debug helper aliases to environment
    cat >> .debug/debug_aliases.sh << 'EOF'
# Debugging shortcuts and utilities
alias gdb-core='gdb -q -c'
alias analyze-core='source ~/.debug/debug_helpers.sh && analyze_core'
alias check-memory='source ~/.debug/debug_helpers.sh && check_leaks'
alias trace-threads='source ~/.debug/debug_helpers.sh && analyze_threads'
alias profile-app='source ~/.debug/debug_helpers.sh && profile_execution'
EOF

    # Create an aggregated debugging profile
    cat > .debug/debug_profile.sh << 'EOF'
#!/bin/sh
# Comprehensive debugging environment setup

# Source all debug configurations
for config in ~/.debug/*.sh; do
    [ -f "$config" ] && . "$config"
done

# Set up debug-specific environment variables
export ASAN_OPTIONS=detect_stack_use_after_return=1:check_initialization_order=1
export UBSAN_OPTIONS=print_stacktrace=1:halt_on_error=1
export LSAN_OPTIONS=verbosity=1:log_threads=1
export TSAN_OPTIONS=second_deadlock_stack=1

# Configure core dumps
ulimit -c unlimited

# Set up debug paths
export DEBUG_PATH="$PWD/.debug"
export PATH="$DEBUG_PATH/tools:$PATH"

echo "Debug environment initialized"
EOF

    # Make debug scripts executable
    chmod +x .debug/*.sh
}

# Create debugging tools for specific scenarios
create_debug_tools() {
    if [ ! -d .debug/tools ]; then
        mkdir -p .debug/tools
fi

#!/bin/zsh

setup_oh_my_zsh() {
    local _username="$1"
    local _user_home="/home/${_username}"

    log_info "Initializing Oh My Zsh environment for user $_username"

    # Define installation paths and configuration files
    local -A PATHS=(
        [OMZ_DIR]="${_user_home}/.oh-my-zsh"
        [ZSHRC]="${_user_home}/.zshrc"
        [CUSTOM_DIR]="${_user_home}/.oh-my-zsh/custom"
        [THEMES_DIR]="${_user_home}/.oh-my-zsh/custom/themes"
        [PLUGINS_DIR]="${_user_home}/.oh-my-zsh/custom/plugins"
    )

    # Define required tools and configurations
    local -A REQUIREMENTS=(
        [zsh]="/usr/local/bin/zsh"
        [git]="/usr/local/bin/git"
        [curl]="/usr/local/bin/curl"
    )

    # Define recommended plugins for development environment
    local _plugins=(
        git
        docker
        kubectl
        fzf
        ripgrep
        zsh-syntax-highlighting
        zsh-autosuggestions
        zsh-completions
    )

    # Validate environment before proceeding
    if ! validate_shell_environment "$_username" "${PATHS[@]}" "${REQUIREMENTS[@]}"; then
        return 1
    }

    # Create backup of existing configuration
    if ! backup_shell_configuration "$_username" "${PATHS[@]}"; then
        return 1
    }

    # Install Oh My Zsh and plugins
    if ! install_oh_my_zsh "$_username" "${PATHS[@]}" "${_plugins[@]}"; then
        return 1
    }

    # Configure shell environment
    if ! configure_shell_environment "$_username" "${PATHS[@]}"; then
        return 1
    }

    # Set up custom configurations
    if ! setup_custom_configuration "$_username" "${PATHS[@]}"; then
        log_warn "Some custom configurations may not have been applied"
    }

    # Verify the setup
    if ! verify_shell_setup "$_username" "${PATHS[@]}"; then
        log_error "Shell environment verification failed"
        return 1
    }

    log_info "Oh My Zsh setup completed successfully for user $_username"
    return 0
}

validate_shell_environment() {
    local _username="$1"
    shift
    local -A _paths=("$@")

    # Verify user exists and has a home directory
    if ! pw user show "$_username" >/dev/null 2>&1; then
        log_error "User $_username does not exist"
        return 1
    }

    # Check for required commands
    local _missing_commands=()
    for cmd in zsh git curl; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            _missing_commands+=("$cmd")
        fi
    done

    if [[ ${#_missing_commands[@]} -gt 0 ]]; then
        log_error "Missing required commands: ${_missing_commands[*]}"
        log_info "Install missing tools using: pkg install -y ${_missing_commands[*]}"
        return 1
    }

    return 0
}

install_oh_my_zsh() {
    local _username="$1"
    shift
    local -A _paths=("$@")
    shift "${#_paths[@]}"
    local _plugins=("$@")

    # Install Oh My Zsh if not already present
    if [[ ! -d "${_paths[OMZ_DIR]}" ]]; then
        log_info "Installing Oh My Zsh for user $_username"

        # Clone Oh My Zsh repository
        if ! sudo -u "$_username" git clone -c core.eol=lf -c core.autocrlf=false \
            https://github.com/ohmyzsh/ohmyzsh.git "${_paths[OMZ_DIR]}"; then
            log_error "Failed to clone Oh My Zsh repository"
            return 1
        }
    else
        log_info "Oh My Zsh already installed, updating..."
        if ! sudo -u "$_username" git -C "${_paths[OMZ_DIR]}" pull; then
            log_warn "Failed to update Oh My Zsh"
        fi
    }

    # Install recommended plugins
    for plugin in "${_plugins[@]}"; do
        local _plugin_dir="${_paths[PLUGINS_DIR]}/${plugin}"
        if [[ ! -d "$_plugin_dir" ]]; then
            log_info "Installing plugin: $plugin"
            case "$plugin" in
                zsh-syntax-highlighting)
                    sudo -u "$_username" git clone \
                        https://github.com/zsh-users/zsh-syntax-highlighting.git "$_plugin_dir"
                    ;;
                zsh-autosuggestions)
                    sudo -u "$_username" git clone \
                        https://github.com/zsh-users/zsh-autosuggestions.git "$_plugin_dir"
                    ;;
                zsh-completions)
                    sudo -u "$_username" git clone \
                        https://github.com/zsh-users/zsh-completions.git "$_plugin_dir"
                    ;;
            esac
        fi
    done

    return 0
}

configure_shell_environment() {
    local _username="$1"
    shift
    local -A _paths=("$@")

    # Create enhanced Zsh configuration
    cat > "${_paths[ZSHRC]}" << EOL
# Enhanced Zsh Configuration for FreeBSD Development
# Generated: $(date)

# Oh My Zsh Configuration
export ZSH="${_paths[OMZ_DIR]}"
export LANG=en_US.UTF-8
export EDITOR='nvim'
export VISUAL='nvim'

# History Configuration
HISTSIZE=1000000
SAVEHIST=1000000
HISTFILE=~/.zsh_history
setopt HIST_IGNORE_DUPS
setopt HIST_IGNORE_SPACE
setopt HIST_VERIFY
setopt INC_APPEND_HISTORY
setopt SHARE_HISTORY

# Path Configuration
path=(
    $HOME/bin
    $HOME/.local/bin
    /usr/local/bin
    /usr/local/sbin
    $path
)

# Plugin Configuration
plugins=(
    git
    docker
    kubectl
    fzf
    ripgrep
    zsh-syntax-highlighting
    zsh-autosuggestions
    zsh-completions
)

# Theme Configuration
ZSH_THEME="powerlevel10k/powerlevel10k"

# Source Oh My Zsh
source \$ZSH/oh-my-zsh.sh

# Development Environment Configuration
source \$HOME/.dev_profile 2>/dev/null

# FreeBSD-specific Aliases
alias portsnap='sudo portsnap'
alias pkg='sudo pkg'
alias services='service -e'
alias ports='cd /usr/ports'
alias src='cd /usr/src'

# Development Aliases
alias g='git'
alias d='docker'
alias k='kubectl'
alias vim='nvim'
alias code='code-insiders'

# Enhanced Directory Navigation
alias ...='cd ../..'
alias ....='cd ../../..'
alias .....='cd ../../../..'

# System Information
alias sysinfo='freebsd-version; uname -a; uptime'
alias meminfo='top -t'
alias diskinfo='df -h'

# Custom Functions
mkcd() { mkdir -p "\$1" && cd "\$1" }
extract() {
    if [ -f \$1 ]; then
        case \$1 in
            *.tar.bz2) tar xjf \$1 ;;
            *.tar.gz)  tar xzf \$1 ;;
            *.bz2)     bunzip2 \$1 ;;
            *.rar)     unrar x \$1 ;;
            *.gz)      gunzip \$1 ;;
            *.tar)     tar xf \$1 ;;
            *.tbz2)    tar xjf \$1 ;;
            *.tgz)     tar xzf \$1 ;;
            *.zip)     unzip \$1 ;;
            *.Z)       uncompress \$1 ;;
            *.7z)      7z x \$1 ;;
            *)         echo "'\$1' cannot be extracted" ;;
        esac
    else
        echo "'\$1' is not a valid file"
    fi
}

# Load custom configurations
for config in \$HOME/.zsh.d/*.zsh(N); do
    source \$config
done

# Initialize completion system
autoload -Uz compinit
compinit -d ~/.cache/zcompdump
EOL

    # Set proper ownership
    chown "${_username}:wheel" "${_paths[ZSHRC]}"
    chmod 644 "${_paths[ZSHRC]}"

    return 0
}

setup_custom_configuration() {
    local _username="$1"
    shift
    local -A _paths=("$@")

    # Create custom configuration directory
    mkdir -p "${_paths[CUSTOM_DIR]}/themes"
    mkdir -p "${_paths[CUSTOM_DIR]}/plugins"

    # Install Powerlevel10k theme
    if [[ ! -d "${_paths[CUSTOM_DIR]}/themes/powerlevel10k" ]]; then
        sudo -u "$_username" git clone --depth=1 \
            https://github.com/romkatv/powerlevel10k.git \
            "${_paths[CUSTOM_DIR]}/themes/powerlevel10k"
    fi

    return 0
}

verify_shell_setup() {
    local _username="$1"
    shift
    local -A _paths=("$@")

    # Verify critical components
    local _failed=0

    # Check Oh My Zsh installation
    if [[ ! -d "${_paths[OMZ_DIR]}" ]]; then
        log_error "Oh My Zsh directory not found"
        _failed=$((_failed + 1))
    fi

    # Check Zsh configuration
    if [[ ! -f "${_paths[ZSHRC]}" ]]; then
        log_error "Zsh configuration file not found"
        _failed=$((_failed + 1))
    fi

    # Verify shell change
    if [[ "$(getent passwd "$_username" | cut -d: -f7)" != "/usr/local/bin/zsh" ]]; then
        log_warn "Default shell is not set to Zsh"
        chsh -s /usr/local/bin/zsh "$_username" || _failed=$((_failed + 1))
    fi

    return $((_failed > 0))
}

# Main function with comprehensive system setup
main() {
    log_info "Starting FreeBSD system configuration with enhanced features"

    # Verify root privileges immediately
    if [[ $(id -u) -ne 0 ]]; then
        log_error "This script must be run as root"
        exit 1
    }

    # Validate username parameter
    if [[ -z "$USERNAME" ]]; then
        log_error "USERNAME environment variable must be set"
        exit 1
    }

    # Create secure log file with proper permissions
    install -m 600 /dev/null "$LOG_FILE"
    chown root:wheel "$LOG_FILE"

    # Define configuration steps in correct dependency order
    local _steps=(
        # Foundation layer - system verification and base packages
        "check_system_resources"         # Must run firs to verify resource requirements are met
        "verify_network_connectivity"    # Must run first to verify network connectivity
        "verify_system_requirements"     # Must run first to check basic requirements
        "install_packages"               # Install required packages before configuration

        # Security layer - core security configuration
        "configure_comprehensive_security"  # Set up base security before other services
        "configure_ssh"                    # Secure remote access configuration

        # System optimization layer
        "configure_system_performance"     # Basic system tuning
        "optimize_network"                 # Network stack optimization

        # Directory structure and environment setup
        "create_all_directories"           # Create required directory structure
        "setup_development"                # Set up development environment
        "configure_kernel_development"      # Configure kernel development environment

        # Service configuration layer
        "configure_nginx"                  # Web server configuration
        "configure_container_environment"   # Container support
        "configure_testing_environment"     # Testing infrastructure

        # Shell environment setup - must come after directory creation
        "setup_zsh"                        # Basic ZSH configuration
        "setup_oh_my_zsh"                  # Oh My Zsh installation and configuration

        # Development tools - depends on shell environment
        "setup_neovim"                     # Editor configuration

        # Monitoring and maintenance - should be last
        "setup_backup_system"              # Configure backup system
        "monitor_system_health"            # Set up system monitoring
    )

    # Execute configuration steps with enhanced error handling
    local _failed=0
    local _critical_steps=(
        "verify_system_requirements"
        "install_packages"
        "configure_comprehensive_security"
        "create_all_directories"
    )

    for _step in "${_steps[@]}"; do
        log_info "Executing system configuration step: $_step"

        # Create checkpoint for critical steps
        if [[ " ${_critical_steps[@]} " =~ " ${_step} " ]]; then
            log_info "Executing critical step: $_step"
            if ! "$_step" "$USERNAME"; then
                log_error "Critical step failed: $_step"
                exit 1
            fi
            continue
        }

        # Execute non-critical steps with warning collection
        if ! "$_step" "$USERNAME"; then
            log_error "Failed during $_step"
            _failed=$((_failed + 1))

            # Record failure details
            echo "$(date '+%Y-%m-%d %H:%M:%S'): Failed step: $_step" >> "${LOG_FILE}.failures"
        fi
    done

    # Ensure file system synchronization
    sync

    # Create final system state snapshot
    if command -v freebsd-version >/dev/null 2>&1; then
        {
            echo "System Configuration Summary"
            echo "=========================="
            echo "Timestamp: $(date)"
            echo "FreeBSD Version: $(freebsd-version)"
            echo "Kernel Version: $(uname -r)"
            echo "Configuration Status: $((_failed > 0 ? "Partial" : "Complete"))"
            echo "Failed Steps: $_failed"
            echo "Log Location: $LOG_FILE"
        } > "${LOG_FILE}.summary"
    fi

    # Final status reporting
    if [[ $_failed -eq 0 ]]; then
        log_info "System configuration completed successfully"
        log_info "Configuration summary available at ${LOG_FILE}.summary"
        log_info "System is ready for reboot when convenient"
        return 0
    else
        log_warn "System configuration completed with $_failed warnings/errors"
        log_warn "Please review logs at $LOG_FILE and ${LOG_FILE}.failures before proceeding"
        return 1
    fi

    # Add service verification step
    if ! verify_all_services; then
        log_error "One or more services failed verification"
        # Generate service status report
        {
            echo "Service Status Report"
            echo "===================="
            echo "Generated: $(date)"
            echo
            echo "Service Status Summary:"
            service -e | while read -r service; do
                printf "%-20s: %s\n" "$service" "$(service "$service" status 2>&1)"
            done
            echo
            echo "Port Status:"
            sockstat -l
            echo
            echo "System Resources:"
            top -b -n 1
        } > "/var/log/service_status_$(date +%Y%m%d_%H%M%S).log"
        return 1

        #Generate final log summary
        generate_log_summary
    fi
}

# Execute main function with proper error handling
if ! main "$@"; then
    log_error "System configuration failed"
    exit 1
fi