#!/usr/local/bin/bash
# ------------------------------------------------------------------------------
#        ______                  ______
#        ___  /_ ______ ____________  /_ _______________
#        __  __ \_  __ `/__  ___/__  __ \__  ___/_  ___/
#    ___ _  /_/ // /_/ / _(__  ) _  / / /_  /    / /__
#    _(_)/_.___/ \__,_/  /____/  /_/ /_/ /_/     \___/
#
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# 1. Early return if not running interactively
# ------------------------------------------------------------------------------
case $- in
    *i*) ;;
      *) return;;
esac

# 1. Environment variables
# ------------------------------------------------------------------------------

# Function to add directories to PATH without duplicates
add_to_path() {
    if [[ ":$PATH:" != *":$1:"* ]]; then
        export PATH="$1:$PATH"
    fi
}

# Add directories to PATH using the function
add_to_path "/usr/local/bin"
add_to_path "/usr/local/sbin"
add_to_path "$HOME/.local/bin"

# Set XDG directories for better standards compliance
export XDG_CONFIG_HOME="$HOME/.config"
export XDG_DATA_HOME="$HOME/.local/share"
export XDG_CACHE_HOME="$HOME/.cache"

# Set editor and pager
export EDITOR="/usr/local/bin/nvim"
export VISUAL="/usr/local/bin/nvim"
export PAGER="less"

# Set locale
export LANG="en_US.UTF-8"
export LC_ALL="en_US.UTF-8"

# Set timezone
export TZ="America/New_York"

# Set terminal type
export TERM="xterm-256color"

# Set history settings
export HISTSIZE=100000
export HISTFILESIZE=200000
export HISTFILE="$HOME/.bash_history"
export HISTCONTROL=ignoreboth
export HISTTIMEFORMAT="%F %T "

# Set LESS options
export LESS="-R -X -F"

# ------------------------------------------------------------------------------
# 1. Greeting
# ------------------------------------------------------------------------------
neofetch
echo "-----------------------------------"
echo "Welcome, $USER!"
echo "Today is $(date)"
echo "Hostname: $(hostname)"
echo "Uptime: $(uptime)"
echo "OS: $(uname -sr)"
echo "-----------------------------------"

# ------------------------------------------------------------------------------
# 2. pyenv initialization
# ------------------------------------------------------------------------------
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"

if command -v pyenv 1>/dev/null 2>&1; then
    eval "$(pyenv init --path)"
    eval "$(pyenv init -)"
fi

# ------------------------------------------------------------------------------
# 4. Less (pager) setup
# ------------------------------------------------------------------------------
# FreeBSD specific lesspipe location
if [ -x /usr/local/bin/lesspipe.sh ]; then
    export LESSOPEN="|/usr/local/bin/lesspipe.sh %s"
fi

# ------------------------------------------------------------------------------
# 5. Bash prompt (PS1) with Nord color theme
# ------------------------------------------------------------------------------
case "$TERM" in
    xterm-color|*-256color) color_prompt=yes;;
esac

force_color_prompt=yes

if [ -n "$force_color_prompt" ]; then
    if [ -x /usr/local/bin/tput ] && tput setaf 1 >&/dev/null; then
        color_prompt=yes
    else
        color_prompt=
    fi
fi

if [ "$color_prompt" = yes ]; then
    PS1='\[\033[38;2;136;192;208m\]\u@\h\[\033[00m\]:\[\033[38;2;94;129;172m\]\w\[\033[00m\]\$ '
else
    PS1='\u@\h:\w\$ '
fi
unset color_prompt force_color_prompt

case "$TERM" in
    xterm*|rxvt*)
        PS1="\[\e]0;\u@\h: \w\a\]$PS1"
        ;;
    *)
        ;;
esac

# ------------------------------------------------------------------------------
# 6. Color support for FreeBSD ls and other commands
# ------------------------------------------------------------------------------
# FreeBSD ls colors
export CLICOLOR=1
export LSCOLORS="ExGxFxdxCxDxDxhbadExEx"

# Colorized grep (FreeBSD style)
alias grep='grep --color=auto'
alias egrep='egrep --color=auto'
alias fgrep='fgrep --color=auto'

# ------------------------------------------------------------------------------
# 7. FreeBSD-specific aliases
# ------------------------------------------------------------------------------
# Basic ls aliases (FreeBSD style)
alias ll='ls -hlAF'
alias la='ls -A'
alias l='ls -CF'

# System management
alias ports-update='sudo portsnap fetch update'
alias pkg-update='sudo pkg update && sudo pkg upgrade'

# ------------------------------------------------------------------------------
# 8. Python virtual environment functions
# ------------------------------------------------------------------------------
alias venv='setup_venv'
alias v='enable_venv'

setup_venv() {
    if type deactivate &>/dev/null; then
        echo "Deactivating current virtual environment..."
        deactivate
    fi

    echo "Creating a new virtual environment in $(pwd)/.venv..."
    python3 -m venv .venv

    echo "Activating the virtual environment..."
    source .venv/bin/activate

    if [ -f requirements.txt ]; then
        echo "Installing dependencies from requirements.txt..."
        pip install -r requirements.txt
    else
        echo "No requirements.txt found. Skipping pip install."
    fi

    echo "Virtual environment setup complete."
}

enable_venv() {
    if type deactivate &>/dev/null; then
        echo "Deactivating current virtual environment..."
        deactivate
    fi

    if [ ! -d ".venv" ]; then
        echo "No virtual environment found in current directory."
        return 1
    fi

    echo "Activating the virtual environment..."
    source .venv/bin/activate

    if [ -f requirements.txt ]; then
        echo "Installing dependencies from requirements.txt..."
        pip install -r requirements.txt
    else
        echo "No requirements.txt found. Skipping pip install."
    fi

    echo "Virtual environment setup complete."
}

# ------------------------------------------------------------------------------
# 10. Bash completion (FreeBSD specific)
# ------------------------------------------------------------------------------
if [ -f /usr/local/share/bash-completion/bash_completion.sh ]; then
    . /usr/local/share/bash-completion/bash_completion.sh
fi

# ------------------------------------------------------------------------------
# 12. Git prompt integration
# ------------------------------------------------------------------------------
if [ -f /usr/local/share/git-core/contrib/completion/git-prompt.sh ]; then
    . /usr/local/share/git-core/contrib/completion/git-prompt.sh
    export GIT_PS1_SHOWDIRTYSTATE=1
    export GIT_PS1_SHOWUNTRACKEDFILES=1
    export GIT_PS1_SHOWUPSTREAM="auto"
    PS1='\[\033[38;2;136;192;208m\]\u@\h\[\033[00m\]:\[\033[38;2;94;129;172m\]\w\[\033[38;2;143;188;187m\]$(__git_ps1 " (%s)")\[\033[00m\]\$ '
fi

# Git aliases
alias gs='git status'
alias ga='git add'
alias gc='git commit'
alias gd='git diff'
alias gl='git log --oneline --graph --decorate'
alias gco='git checkout'
alias gpu='git pull'
alias gp='git push'

# ------------------------------------------------------------------------------
# 13. Extractor function
# ------------------------------------------------------------------------------
extract() {
    if [ -f "$1" ]; then
        case "$1" in
            *.tar.bz2)   tar xvjf "$1"    ;;
            *.tar.gz)    tar xvzf "$1"    ;;
            *.bz2)       bunzip2 "$1"     ;;
            *.rar)       unrar x "$1"     ;;
            *.gz)        gunzip "$1"      ;;
            *.tar)       tar xvf "$1"     ;;
            *.tbz2)      tar xvjf "$1"    ;;
            *.tgz)       tar xvzf "$1"    ;;
            *.zip)       unzip "$1"       ;;
            *.Z)         uncompress "$1"  ;;
            *.7z)        7z x "$1"        ;;
            *.xz)        unxz "$1"        ;;
            *.lzma)      unlzma "$1"      ;;
            *.tar.xz)    tar xvf "$1"     ;;
            *.tar.lzma)  tar xvf "$1"     ;;
            *.tar.Z)     tar xvf "$1"     ;;
            *.tar.lz)    tar xvf "$1"     ;;
            *.lz)        lzip -d "$1"     ;;
            *.zst)       zstd -d "$1"     ;;
            *.tar.zst)   tar --zstd -xvf "$1" ;;
            *)           echo "Unable to extract '$1'" ;;
        esac
    else
        echo "'$1' is not a valid file"
    fi
}

# ------------------------------------------------------------------------------
# End of ~/.bashrc
# ------------------------------------------------------------------------------