#!/bin/bash
# ~/.bashrc – Enhanced Bash configuration for Debian

# =============================================================================
# Guard: Only run if using Bash.
# =============================================================================
if [ -z "$BASH_VERSION" ]; then
    # Not Bash – do nothing.
    return
fi

# =============================================================================
# Exit if not running interactively
# =============================================================================
[[ $- != *i* ]] && return

# =============================================================================
# 1. Environment Variables & Shell Options
# =============================================================================
# Prepend essential directories to PATH
export PATH="/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin:$HOME/.local/bin:$HOME/bin:$PATH"

# Enable useful Bash options
shopt -s checkwinsize histappend cmdhist autocd cdspell dirspell globstar nocaseglob extglob histverify

# XDG Base Directories
export XDG_CONFIG_HOME="$HOME/.config"
export XDG_DATA_HOME="$HOME/.local/share"
export XDG_CACHE_HOME="$HOME/.cache"
export XDG_STATE_HOME="$HOME/.local/state"

# Set default editor and pager
if command -v nvim >/dev/null 2>&1; then
    export EDITOR="nvim"
    export VISUAL="nvim"
    alias vim="nvim"
    alias vi="nvim"
elif command -v vim >/dev/null 2>&1; then
    export EDITOR="vim"
    export VISUAL="vim"
    alias vi="vim"
fi
export PAGER="less"

# Locale and Timezone (adjust TZ as needed)
export LANG="en_US.UTF-8"
export LC_ALL="en_US.UTF-8"
export TZ="America/New_York"

# Force 256-color mode for xterm if needed
[[ "$TERM" == "xterm" ]] && export TERM="xterm-256color"

# =============================================================================
# 2. Nord Color Scheme for Prompt and LESS Customization
# =============================================================================
# Nord palette variables
NORD4="\[\033[38;2;216;222;233m\]"   # Snow Storm: #D8DEE9
NORD5="\[\033[38;2;229;233;240m\]"   # Snow Storm: #E5E9F0
NORD6="\[\033[38;2;236;239;244m\]"   # Snow Storm: #ECEFF4
NORD7="\[\033[38;2;143;188;187m\]"   # Frost: #8FBCBB
NORD8="\[\033[38;2;136;192;208m\]"   # Frost: #88C0D0
NORD9="\[\033[38;2;129;161;193m\]"   # Frost: #81A1C1
NORD10="\[\033[38;2;94;129;172m\]"   # Frost: #5E81AC
NORD11="\[\033[38;2;191;97;106m\]"   # Aurora: #BF616A
NORD12="\[\033[38;2;208;135;112m\]"   # Aurora: #D08770
NORD13="\[\033[38;2;235;203;139m\]"   # Aurora: #EBCB8B
NORD14="\[\033[38;2;163;190;140m\]"   # Aurora: #A3BE8C
NORD15="\[\033[38;2;180;142;173m\]"   # Aurora: #B48EAD
RESET="\[\e[0m\]"

# Customize LESS colors with Nord palette
export LESS="-R -X -F -i -J --mouse"
export LESS_TERMCAP_mb=$'\e[38;2;191;97;106m'
export LESS_TERMCAP_md=$'\e[38;2;136;192;208m'
export LESS_TERMCAP_me=$'\e[0m'
export LESS_TERMCAP_so=$'\e[38;2;235;203;139m'
export LESS_TERMCAP_se=$'\e[0m'
export LESS_TERMCAP_us=$'\e[38;2;163;190;140m'
export LESS_TERMCAP_ue=$'\e[0m'

# =============================================================================
# 3. Enhanced History Settings
# =============================================================================
export HISTSIZE=1000000
export HISTFILESIZE=2000000
export HISTFILE="$HOME/.bash_history"
export HISTCONTROL="ignoreboth:erasedups"
export HISTTIMEFORMAT="%F %T "

# =============================================================================
# 4. System Information & Greeting
# =============================================================================
# Display system info if fastfetch is installed
command -v fastfetch >/dev/null 2>&1 && fastfetch

# =============================================================================
# 5. Development Environment Setup
# =============================================================================
# Initialize Pyenv if installed
if [ -d "$HOME/.pyenv" ]; then
    export PYENV_ROOT="$HOME/.pyenv"
    export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init --path)"
    eval "$(pyenv init -)"
fi

# =============================================================================
# 6. LESS (Pager) Setup
# =============================================================================
if [ -x /usr/bin/lesspipe ]; then
    eval "$(SHELL=/bin/sh lesspipe)"
fi

# =============================================================================
# 7. Prompt Customization – Nord-Themed Single-Line Prompt
# =============================================================================
USERNAME_COLOR="\[\033[38;2;143;188;187m\]"   # Nord7 – Frost
HOSTNAME_COLOR="\[\033[38;2;143;188;187m\]"   # Nord7 – Frost
DIR_COLOR="\[\033[38;2;129;161;193m\]"          # Nord9 – Frost
PROMPT_ICON="\[\033[38;2;94;129;172m\]>"         # Nord10 – Darker blue

export PS1="[${USERNAME_COLOR}\u${RESET}@${HOSTNAME_COLOR}\h${RESET}] [${DIR_COLOR}\w${RESET}] ${PROMPT_ICON}${NORD6} "

# =============================================================================
# 8. Colorized Output for Common Commands
# =============================================================================
if command -v dircolors >/dev/null 2>&1; then
    if [ -r "$HOME/.dircolors" ]; then
        eval "$(dircolors -b "$HOME/.dircolors")"
    else
        eval "$(dircolors -b)"
    fi
    alias ls='ls --color=auto'
    alias dir='dir --color=auto'
    alias vdir='vdir --color=auto'
    alias grep='grep --color=auto'
    alias fgrep='fgrep --color=auto'
    alias egrep='egrep --color=auto'
    alias diff='diff --color=auto'
    alias ip='ip --color=auto'
fi

# =============================================================================
# 9. Aliases & Shortcuts (including Debian Package Management)
# =============================================================================
# Directory navigation
alias ll='ls -lah'
alias la='ls -A'
alias l='ls -CF'
alias ..='cd ..'
alias ...='cd ../..'
alias ....='cd ../../..'
alias .....='cd ../../../..'

# Debian package management using apt
alias update='sudo apt update && sudo apt upgrade -y'
alias install='sudo apt install -y'
alias remove='sudo apt remove -y'
alias search='apt search'

# Safety aliases
alias rm='rm -i'
alias cp='cp -i'
alias mv='mv -i'
alias mkdir='mkdir -p'

# Git shortcuts
alias gs='git status'
alias ga='git add'
alias gc='git commit'
alias gp='git push'
alias gl='git pull'
alias gd='git diff'
alias glog='git log --oneline --graph --decorate'

# General useful shortcuts
alias h='history'
alias j='jobs -l'
alias path='echo -e ${PATH//:/\\n}'
alias now='date +"%T"'
alias nowdate='date +"%d-%m-%Y"'
alias ports='ss -tulanp'
alias mem='free -h'
alias disk='df -h'

# Docker shortcuts
alias d='docker'
alias dc='docker-compose'
alias dps='docker ps'
alias di='docker images'

# Miscellaneous
alias sudo='sudo '   # Ensure aliases work with sudo
alias watch='watch '

# =============================================================================
# 10. Enhanced Functions
# =============================================================================
# Create and activate a Python virtual environment
setup_venv() {
    local venv_name="${1:-.venv}"
    # Deactivate any active virtual environment
    type deactivate &>/dev/null && deactivate
    if [ ! -d "$venv_name" ]; then
        echo "Creating virtual environment in $venv_name..."
        python3 -m venv "$venv_name"
    fi
    source "$venv_name/bin/activate"
    [ -f "requirements.txt" ] && pip install -r requirements.txt
    [ -f "requirements-dev.txt" ] && pip install -r requirements-dev.txt
}
alias venv='setup_venv'

# Universal archive extraction function
extract() {
    if [ -z "$1" ]; then
        echo "Usage: extract <archive>"
        return 1
    fi
    if [ ! -f "$1" ]; then
        echo "File '$1' not found."
        return 1
    fi
    case "$1" in
        *.tar.bz2)   tar xjf "$1" ;;
        *.tar.gz)    tar xzf "$1" ;;
        *.bz2)       bunzip2 "$1" ;;
        *.rar)       unrar x "$1" ;;
        *.gz)        gunzip "$1" ;;
        *.tar)       tar xf "$1" ;;
        *.tbz2)      tar xjf "$1" ;;
        *.tgz)       tar xzf "$1" ;;
        *.zip)       unzip "$1" ;;
        *.Z)         uncompress "$1" ;;
        *.7z)        7z x "$1" ;;
        *.xz)        unxz "$1" ;;
        *.tar.xz)    tar xf "$1" ;;
        *.tar.zst)   tar --zstd -xf "$1" ;;
         *) echo "Cannot extract '$1'"; return 1 ;;
    esac
}

# Create a directory and change into it
mkcd() {
    mkdir -p "$1" && cd "$1" || return 1
}

# Search for files and directories by pattern
ff() { find . -type f -iname "*$1*"; }
fd() { find . -type d -iname "*$1*"; }

# Quickly back up a file with a timestamped .bak extension
bak() { cp "$1" "${1}.bak.$(date +%Y%m%d_%H%M%S)"; }

# Create and switch to a temporary directory
mktempdir() {
    local tmpdir
    tmpdir=$(mktemp -d -t tmp.XXXXXX)
    echo "Created temporary directory: $tmpdir"
    cd "$tmpdir" || return
}

# Serve the current directory over HTTP (default port 8000)
serve() {
    local port="${1:-8000}"
    echo "Serving HTTP on port ${port}..."
    python3 -m http.server "$port"
}

# =============================================================================
# 11. Bash Completion
# =============================================================================
if ! shopt -oq posix; then
    if [ -f /usr/share/bash-completion/bash_completion ]; then
        . /usr/share/bash-completion/bash_completion
    elif [ -f /etc/bash_completion ]; then
        . /etc/bash_completion
    fi
fi

# =============================================================================
# 12. Local Customizations & Additional Settings
# =============================================================================
# Source a local bashrc file if it exists
[ -f "$HOME/.bashrc.local" ] && . "$HOME/.bashrc.local"

# Auto-load additional shell scripts from ~/.bashrc.d/
if [ -d "$HOME/.bashrc.d" ]; then
    for file in "$HOME"/.bashrc.d/*.sh; do
        [ -r "$file" ] && . "$file"
    done
fi

# Source additional environment settings if available
[ -f "$HOME/.local/bin/env" ] && . "$HOME/.local/bin/env"

# =============================================================================
# 13. Final PROMPT_COMMAND Consolidation
# =============================================================================
export PROMPT_COMMAND='history -a; echo "\n[$(date)] ${USER}@${HOSTNAME}:${PWD}\n" >> ~/.bash_sessions.log'

# =============================================================================
# End of ~/.bashrc
# =============================================================================
