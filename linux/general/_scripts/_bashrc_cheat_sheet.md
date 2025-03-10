# Ubuntu Bash Configuration Guide & Cheat Sheet

## Table of Contents

1. [Introduction](#introduction)
2. [Custom Bash Configuration Overview](#custom-bash-configuration-overview)
3. [SSH Machine Selector Tool](#ssh-machine-selector-tool)
4. [Package Management](#package-management)
5. [Navigation & File Management](#navigation--file-management)
6. [System Information & Monitoring](#system-information--monitoring)
7. [Development Tools](#development-tools)
8. [Git Shortcuts](#git-shortcuts)
9. [Docker Shortcuts](#docker-shortcuts)
10. [Utility Functions](#utility-functions)
11. [Directory Bookmarks](#directory-bookmarks)
12. [SSH Key Management](#ssh-key-management)
13. [System Maintenance](#system-maintenance)
14. [Quick Reference Cards](#quick-reference-cards)

## Introduction

This guide covers the custom Bash configuration in your Ubuntu system, featuring enhanced productivity tools, shortcuts, and the SSH Machine Selector. The configuration uses a Nord color theme and includes numerous aliases and functions to streamline your command-line workflow.

## Custom Bash Configuration Overview

Your `~/.bashrc` configuration provides an enhanced terminal experience with:

- **Nord Theme** color scheme for improved readability
- **Command history** management and persistence
- **Convenience aliases** for common operations
- **Enhanced prompt** with user, hostname, and directory information
- **Custom functions** for common development and system tasks

## SSH Machine Selector Tool

The SSH Machine Selector tool provides a menu-driven interface to connect to your machines.

### Usage

Simply type:

```bash
ssh
```

This launches the machine selector interface that displays:

- Available machines with hostname, IP address, OS, and status
- Numbered menu for quick selection

### Features

- Select a machine by number to connect via SSH
- Option to use a different username than default
- Full-screen terminal interface with proper SSH handoff
- Accessible via the standard `ssh` command

### Alternative SSH Access

To use the original SSH command directly:

```bash
ssh-orig user@hostname
```

## Package Management

### Nala (APT Enhancement)

```bash
update          # Update and upgrade all packages
install package # Install a package
remove package  # Remove a package
autoremove      # Remove unused dependencies
search term     # Search for packages
clean           # Clean package cache and remove unused packages
```

### Package Information

```bash
apt show package   # Show package details
apt depends package # Show package dependencies
apt policy package # Show package installation sources and versions
```

## Navigation & File Management

### Directory Navigation

```bash
..       # Go up one directory
...      # Go up two directories
....     # Go up three directories
.....    # Go up four directories
cd..     # Go up one directory (alternative)
cd -     # Go to previous directory
```

### File Operations

```bash
ls       # List files with colors
ll       # List all files with details
la       # List all files
l        # List files in columns

mkdir -p dir/subdir  # Create nested directories
cp -i source dest    # Copy with confirmation
mv -i source dest    # Move with confirmation
rm -i file           # Remove with confirmation

df -h    # Disk usage in human-readable format
du -h    # Directory size in human-readable format
```

### File Finding

```bash
ff pattern  # Find files matching pattern
fd pattern  # Find directories matching pattern
```

### File Extraction

```bash
extract archive.tar.gz  # Extract any supported archive format
```

## System Information & Monitoring

### System Stats

```bash
free -h        # Memory usage in human-readable format
df -h          # Disk usage in human-readable format
cpu            # Current CPU usage percentage
disk           # Show disk usage (excludes temporary filesystems)
now            # Current time
nowdate        # Current date
```

### Network Information

```bash
myip           # Show your public IP address
localip        # Show your local IP address
ports          # List all listening ports
ports-in-use   # Show detailed list of ports in use
speedtest      # Run a network speed test
ping host      # Ping host (5 packets)
webserver      # Start a web server in current directory
weather        # Show current weather
```

## Development Tools

### Python Environment

```bash
venv [name]    # Create/activate Python virtual environment
python file.py # Run Python file with sudo & pyenv
```

### Node.js (NVM)

```bash
nvm ls         # List installed Node.js versions
nvm use version # Use specific Node.js version
nvm install version # Install Node.js version
```

### Web Development

```bash
serve [port]   # Start a web server on specified port (default: 8000)
```

## Git Shortcuts

```bash
gs      # git status
ga      # git add
gc      # git commit
gp      # git push
gl      # git pull
gd      # git diff
gco     # git checkout
gb      # git branch
gm      # git merge
gr      # git remote -v
gf      # git fetch
glog    # git log with graph
gsw     # git switch
```

## Docker Shortcuts

```bash
d       # docker
dc      # docker-compose
dps     # docker ps (list containers)
di      # docker images (list images)
drm     # docker rm (remove container)
drmi    # docker rmi (remove image)
dexec   # docker exec -it (interactive shell)
dlogs   # docker logs
dstop   # docker stop
dstart  # docker start
dc-up   # docker-compose up -d
dc-down # docker-compose down
dc-logs # docker-compose logs -f
```

## Utility Functions

### File & Directory Management

```bash
mkcd dir       # Create directory and cd into it
bak file       # Create timestamped backup of file
mktempdir      # Create and cd into temporary directory
```

### General Utilities

```bash
transfer file  # Upload and share file via transfer.sh
calc "1 + 2"   # Simple calculator
countdown 60   # Countdown timer in seconds
h              # Show command history
path           # Show PATH entries, one per line
watch command  # Watch command output with updates
```

## Directory Bookmarks

Quickly jump between frequently-used directories:

```bash
mark name      # Bookmark current directory as 'name'
jump name      # Jump to bookmark 'name'
unmark name    # Remove bookmark 'name'
marks          # List all bookmarks
```

## SSH Key Management

```bash
list_ssh_keys              # List and verify all SSH keys
create_ssh_key [name] [email] # Create a new SSH key
```

## System Maintenance

```bash
check_load             # Check current system load
cleanup_system         # Clean package cache and system logs
mem_usage              # Show memory usage by processes
find_large_files [size] # Find large files (default: +100M)
```

## Quick Reference Cards

### Bash Shortcuts

| Shortcut | Description |
|----------|-------------|
| Ctrl+A | Move cursor to beginning of line |
| Ctrl+E | Move cursor to end of line |
| Ctrl+U | Cut text from cursor to beginning of line |
| Ctrl+K | Cut text from cursor to end of line |
| Ctrl+W | Cut previous word |
| Ctrl+Y | Paste previously cut text |
| Ctrl+L | Clear screen |
| Ctrl+R | Search command history |
| Ctrl+C | Cancel current command |
| Ctrl+D | Exit current shell |
| Ctrl+Z | Suspend current process |
| Tab | Auto-complete command, file, or directory |
| ↑/↓ | Navigate command history |
| Alt+. | Insert last argument of previous command |

### Ubuntu System Commands

| Command | Description |
|---------|-------------|
| `sudo apt update` | Update package lists |
| `sudo apt upgrade` | Upgrade installed packages |
| `sudo apt install pkg` | Install package |
| `sudo apt remove pkg` | Remove package |
| `sudo apt autoremove` | Remove unneeded dependencies |
| `sudo systemctl start service` | Start a service |
| `sudo systemctl stop service` | Stop a service |
| `sudo systemctl restart service` | Restart a service |
| `sudo systemctl status service` | Check service status |
| `journalctl -u service` | View service logs |
| `lsb_release -a` | Show Ubuntu version |
| `uname -a` | Show kernel information |
| `lscpu` | CPU information |
| `lsusb` | USB device information |
| `lspci` | PCI device information |
| `lsblk` | Block device information |
