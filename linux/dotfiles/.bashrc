# ------------------------------------------------------------------------------
#        ______                  ______
#        ___  /_ ______ ____________  /_ _______________
#        __  __ \_  __ `/__  ___/__  __ \__  ___/_  ___/
#    ___ _  /_/ // /_/ / _(__  ) _  / / /_  /    / /__
#    _(_)/_.___/ \__,_/  /____/  /_/ /_/ /_/     \___/
#
# ------------------------------------------------------------------------------

# ~/.bashrc: executed by bash(1) for non-login shells.
# ------------------------------------------------------------------------------
# 0. Early return if not running interactively
# ------------------------------------------------------------------------------
case $- in
    *i*) ;;
      *) return;;
esac

# Set initial PATH to include essential system directories
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$HOME/.local/bin:$HOME/bin:$PATH"

# ------------------------------------------------------------------------------
# 1. Environment Variables and Shell Options
# ------------------------------------------------------------------------------

# Enable some useful bash options
shopt -s checkwinsize     # Update window size after each command
shopt -s histappend       # Append to history instead of overwriting
shopt -s cmdhist          # Save multi-line commands as one command
shopt -s autocd           # Change to named directory
shopt -s cdspell          # Autocorrect typos in path names when using `cd`
shopt -s dirspell         # Autocorrect typos in path names when tab-completing
shopt -s globstar         # Pattern ** will match all files and zero or more directories
shopt -s nocaseglob       # Case-insensitive pathname expansion
shopt -s extglob          # Extended pattern matching
shopt -s histverify       # Allow editing of history substitution results

# Nord color scheme as ANSI escape sequences
NORD0="\[\033[38;2;46;52;64m\]"      # Polar Night (darkest)
NORD1="\[\033[38;2;59;66;82m\]"      # Polar Night
NORD2="\[\033[38;2;67;76;94m\]"      # Polar Night
NORD3="\[\033[38;2;76;86;106m\]"     # Polar Night (lightest)
NORD4="\[\033[38;2;216;222;233m\]"   # Snow Storm (darkest)
NORD5="\[\033[38;2;229;233;240m\]"   # Snow Storm
NORD6="\[\033[38;2;236;239;244m\]"   # Snow Storm (lightest)
NORD7="\[\033[38;2;143;188;187m\]"   # Frost (turquoise)
NORD8="\[\033[38;2;136;192;208m\]"   # Frost (light blue)
NORD9="\[\033[38;2;129;161;193m\]"   # Frost (blue)
NORD10="\[\033[38;2;94;129;172m\]"   # Frost (dark blue)
NORD11="\[\033[38;2;191;97;106m\]"   # Aurora (red)
NORD12="\[\033[38;2;208;135;112m\]"  # Aurora (orange)
NORD13="\[\033[38;2;235;203;139m\]"  # Aurora (yellow)
NORD14="\[\033[38;2;163;190;140m\]"  # Aurora (green)
NORD15="\[\033[38;2;180;142;173m\]"  # Aurora (purple)
RESET="\[\e[0m\]"                    # Reset color

# Reset color code
RESET='\[\e[0m\]'

# Set XDG directories (freedesktop.org standard)
export XDG_CONFIG_HOME="$HOME/.config"
export XDG_DATA_HOME="$HOME/.local/share"
export XDG_CACHE_HOME="$HOME/.cache"
export XDG_STATE_HOME="$HOME/.local/state"

# Set editor and pager
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

# Set locale and timezone
export LANG="en_US.UTF-8"
export LC_ALL="en_US.UTF-8"
export TZ="America/New_York"

# Set terminal type
[[ "$TERM" == "xterm" ]] && export TERM="xterm-256color"

# Enhanced history control
export HISTSIZE=1000000
export HISTFILESIZE=2000000
export HISTFILE="$HOME/.bash_history"
export HISTCONTROL="ignoreboth:erasedups"
export HISTTIMEFORMAT="%F %T "
export HISTIGNORE="ls:ll:cd:pwd:bg:fg:history:clear:exit"
PROMPT_COMMAND='history -a'

# Set LESS options with enhanced colors
export LESS="-R -X -F -i -J --mouse"
export LESS_TERMCAP_mb=$'\e[1;31m'     # begin blink (red)
export LESS_TERMCAP_md=$'\e[1;36m'     # begin bold (cyan)
export LESS_TERMCAP_me=$'\e[0m'        # reset bold/blink
export LESS_TERMCAP_so=$'\e[01;44;33m' # begin standout (yellow on blue)
export LESS_TERMCAP_se=$'\e[0m'        # reset standout
export LESS_TERMCAP_us=$'\e[1;32m'     # begin underline (green)
export LESS_TERMCAP_ue=$'\e[0m'        # reset underline

# ------------------------------------------------------------------------------
# 2. System Information and Greeting
# ------------------------------------------------------------------------------
if command -v neofetch >/dev/null 2>&1; then
    neofetch
elif command -v screenfetch >/dev/null 2>&1; then
    screenfetch
fi

# ------------------------------------------------------------------------------
# 3. Development Environment Setup
# ------------------------------------------------------------------------------

# Python environment
if [ -d "$HOME/.pyenv" ]; then
    export PYENV_ROOT="$HOME/.pyenv"
    export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init --path)"
    eval "$(pyenv init -)"
fi

# ------------------------------------------------------------------------------
# 4. Less (pager) setup for Ubuntu
# ------------------------------------------------------------------------------
[ -x /usr/bin/lesspipe ] && eval "$(SHELL=/bin/sh lesspipe)"

# ------------------------------------------------------------------------------
# 5. Simple PS1 with clean Nord colors
# ------------------------------------------------------------------------------
# Convert hex colors to ANSI escape sequences
USERNAME="\[\033[38;2;143;188;187m\]"   # NORD7  - Frost (turquoise)
HOSTNAME="\[\033[38;2;143;188;187m\]"   # NORD7  - Frost (turquoise)
DIR_COLOR="\[\033[38;2;129;161;193m\]"  # NORD9  - Frost (blue)
DELIM="\[\033[38;2;216;222;233m\]"      # NORD4  - Snow Storm (darkest)
ERROR="\[\033[38;2;191;97;106m\]"       # NORD11 - Aurora (red)
RESET="\[\e[0m\]"

# Simple single-line prompt
PS1="${USERNAME}\u${DELIM}@${HOSTNAME}\h${DELIM}:${DIR_COLOR}\w${DELIM} ❯${RESET} "

# ------------------------------------------------------------------------------
# 6. Color support for Linux commands
# ------------------------------------------------------------------------------
if [ -x /usr/bin/dircolors ]; then
    test -r ~/.dircolors && eval "$(dircolors -b ~/.dircolors)" || eval "$(dircolors -b)"
    alias ls='ls --color=auto'
    alias dir='dir --color=auto'
    alias vdir='vdir --color=auto'

    alias grep='grep --color=auto'
    alias fgrep='fgrep --color=auto'
    alias egrep='egrep --color=auto'
    alias diff='diff --color=auto'
    alias ip='ip --color=auto'
fi

# ------------------------------------------------------------------------------
# 7. Enhanced Aliases
# ------------------------------------------------------------------------------
# Directory navigation
alias ll='ls -lah'
alias la='ls -A'
alias l='ls -CF'
alias ..='cd ..'
alias ...='cd ../..'
alias ....='cd ../../..'
alias .....='cd ../../../..'

# System management
alias update='sudo apt update && sudo apt upgrade'
alias install='sudo apt install'
alias remove='sudo apt remove'
alias purge='sudo apt purge'
alias autoremove='sudo apt autoremove'

# Safety nets
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

# Useful shortcuts
alias h='history'
alias j='jobs -l'
alias path='echo -e ${PATH//:/\\n}'
alias now='date +"%T"'
alias nowdate='date +"%d-%m-%Y"'
alias ports='netstat -tulanp'
alias mem='free -h'
alias disk='df -h'

# Docker shortcuts
alias d='docker'
alias dc='docker-compose'
alias dps='docker ps'
alias di='docker images'

# User shortcuts
alias venv='setup_venv'
alias sudo='sudo '
alias watch='watch '

# ------------------------------------------------------------------------------
# 8. Enhanced Functions
# ------------------------------------------------------------------------------

# Create and activate Python virtual environment
setup_venv() {
    local venv_name="${1:-.venv}"
    if type deactivate &>/dev/null; then
        deactivate
    fi

    if [ ! -d "$venv_name" ]; then
        echo "Creating virtual environment in $venv_name..."
        python3 -m venv "$venv_name"
    fi

    source "$venv_name/bin/activate"

    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt
    fi

    if [ -f "requirements-dev.txt" ]; then
        pip install -r requirements-dev.txt
    fi
}

# Improved extract function
extract() {
    if [ -z "$1" ]; then
        echo "Usage: extract <path/file_name>.<zip|rar|bz2|gz|tar|tbz2|tgz|Z|7z|xz|ex|tar.bz2|tar.gz|tar.xz|tar.zst>"
        return 1
    fi

    if [ ! -f "$1" ]; then
        echo "'$1' - file doesn't exist"
        return 1
    fi

    case "$1" in
        *.tar.bz2)   tar xjf "$1"     ;;
        *.tar.gz)    tar xzf "$1"     ;;
        *.bz2)       bunzip2 "$1"     ;;
        *.rar)       unrar x "$1"     ;;
        *.gz)        gunzip "$1"      ;;
        *.tar)       tar xf "$1"      ;;
        *.tbz2)      tar xjf "$1"     ;;
        *.tgz)       tar xzf "$1"     ;;
        *.zip)       unzip "$1"       ;;
        *.Z)         uncompress "$1"  ;;
        *.7z)        7z x "$1"        ;;
        *.xz)        unxz "$1"        ;;
        *.tar.xz)    tar xf "$1"      ;;
        *.tar.zst)   tar --zstd -xf "$1" ;;
        *)
            echo "'$1' cannot be extracted via extract()"
            return 1
            ;;
    esac
}

# Enhanced mkdir and cd
mkcd() {
    mkdir -p "$1" && cd "$1" || return 1
}

# Find file by pattern
ff() {
    find . -type f -iname "*$1*"
}

# Find directory by pattern
fd() {
    find . -type d -iname "*$1*"
}

# Quick backup of a file
bak() {
    cp "$1" "${1}.bak.$(date +%Y%m%d_%H%M%S)"
}

# ------------------------------------------------------------------------------
# 9. Bash Completion for Ubuntu
# ------------------------------------------------------------------------------
if ! shopt -oq posix; then
    if [ -f /usr/share/bash-completion/bash_completion ]; then
        . /usr/share/bash-completion/bash_completion
    elif [ -f /etc/bash_completion ]; then
        . /etc/bash_completion
    fi
fi

# ------------------------------------------------------------------------------
# 10. Local customizations
# ------------------------------------------------------------------------------
# Source local bashrc if it exists
if [ -f ~/.bashrc.local ]; then
    source ~/.bashrc.local
fi

# ------------------------------------------------------------------------------
# End of ~/.bashrc
# ------------------------------------------------------------------------------