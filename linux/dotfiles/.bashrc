# ------------------------------------------------------------------------------
#        ______                  ______
#        ___  /_ ______ ____________  /_ _______________
#        __  __ \_  __ `/__  ___/__  __ \__  ___/_  ___/
#    ___ _  /_/ // /_/ / _(__  ) _  / / /_  /    / /__
#    _(_)/_.___/ \__,_/  /____/  /_/ /_/ /_/     \___/
#
# ------------------------------------------------------------------------------

#!/bin/bash
# ~/.bashrc for OpenSUSE

# ------------------------------------------------------------------------------
# 0. Early Exit for Non‐Interactive Shells
# ------------------------------------------------------------------------------
case $- in
    *i*) ;;
      *) return;;
esac

# ------------------------------------------------------------------------------
# 1. Environment Variables & Shell Options
# ------------------------------------------------------------------------------
# Prepend essential directories to PATH
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$HOME/.local/bin:$HOME/bin:$PATH"

# Enable useful bash options
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

# Locale and Timezone
export LANG="en_US.UTF-8"
export LC_ALL="en_US.UTF-8"
export TZ="America/New_York"

# Force 256-color mode for xterm
[[ "$TERM" == "xterm" ]] && export TERM="xterm-256color"

# Enhanced History Settings
export HISTSIZE=1000000
export HISTFILESIZE=2000000
export HISTFILE="$HOME/.bash_history"
export HISTCONTROL="ignoreboth:erasedups"
export HISTTIMEFORMAT="%F %T "
export HISTIGNORE="ls:ll:cd:pwd:bg:fg:history:clear:exit"
# Append history after each command and update terminal title
PROMPT_COMMAND='history -a; echo -ne "\033]0;${USER}@${HOSTNAME}: ${PWD}\007"'

# ------------------------------------------------------------------------------
# 2. Nord Color Scheme (Lighter Palette Only)
# (Nord0–Nord3 are intentionally omitted for better contrast on dark terminals)
# ------------------------------------------------------------------------------
NORD4="\[\033[38;2;216;222;233m\]"   # Snow Storm: #D8DEE9
NORD5="\[\033[38;2;229;233;240m\]"   # Snow Storm: #E5E9F0
NORD6="\[\033[38;2;236;239;244m\]"   # Snow Storm: #ECEFF4
NORD7="\[\033[38;2;143;188;187m\]"   # Frost: #8FBCBB
NORD8="\[\033[38;2;136;192;208m\]"   # Frost: #88C0D0
NORD9="\[\033[38;2;129;161;193m\]"   # Frost: #81A1C1
NORD10="\[\033[38;2;94;129;172m\]"   # Frost: #5E81AC
NORD11="\[\033[38;2;191;97;106m\]"   # Aurora: #BF616A
NORD12="\[\033[38;2;208;135;112m\]"  # Aurora: #D08770
NORD13="\[\033[38;2;235;203;139m\]"  # Aurora: #EBCB8B
NORD14="\[\033[38;2;163;190;140m\]"  # Aurora: #A3BE8C
NORD15="\[\033[38;2;180;142;173m\]"  # Aurora: #B48EAD
RESET="\[\e[0m\]"

# Customize LESS (pager) colors with Nord palette
export LESS="-R -X -F -i -J --mouse"
export LESS_TERMCAP_mb=$'\e[38;2;191;97;106m'     # Nord11 for blink
export LESS_TERMCAP_md=$'\e[38;2;136;192;208m'     # Nord8 for bold
export LESS_TERMCAP_me=$'\e[0m'
export LESS_TERMCAP_so=$'\e[1;38;2;235;203;139m'   # Nord13 for standout
export LESS_TERMCAP_se=$'\e[0m'
export LESS_TERMCAP_us=$'\e[1;38;2;163;190;140m'   # Nord14 for underline
export LESS_TERMCAP_ue=$'\e[0m'

# ------------------------------------------------------------------------------
# 3. System Information & Greeting
# ------------------------------------------------------------------------------
if command -v neofetch >/dev/null 2>&1; then
    neofetch
elif command -v screenfetch >/dev/null 2>&1; then
    screenfetch
fi

# ------------------------------------------------------------------------------
# 4. Development Environment Setup
# ------------------------------------------------------------------------------
# Initialize Pyenv if installed
if [ -d "$HOME/.pyenv" ]; then
    export PYENV_ROOT="$HOME/.pyenv"
    export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init --path)"
    eval "$(pyenv init -)"
fi

# ------------------------------------------------------------------------------
# 5. Less (Pager) Setup
# ------------------------------------------------------------------------------
[ -x /usr/bin/lesspipe ] && eval "$(SHELL=/bin/sh lesspipe)"

# ------------------------------------------------------------------------------
# 6. Prompt Customization with Git Branch Integration
# ------------------------------------------------------------------------------
# Function to detect current Git branch
parse_git_branch() {
    git symbolic-ref --short HEAD 2>/dev/null | sed "s/^/ (${NORD13//\\[/\\[})/; s/$/${RESET}/"
}
# Build the prompt using Nord colors:
# • Username & hostname in Nord7, directory in Nord9, delimiters in Nord4.
PROMPT_USER="${NORD7}\u"
PROMPT_HOST="${NORD7}\h"
PROMPT_DIR="${NORD9}\w"
PROMPT_DELIM="${NORD4}:"
PROMPT_GIT='$(parse_git_branch)'
PROMPT_SYMBOL="${NORD4} ❯${RESET} "
PS1="${PROMPT_USER}${NORD4}@${PROMPT_HOST}${PROMPT_DELIM}${PROMPT_DIR}${PROMPT_GIT}${PROMPT_DELIM} ${PROMPT_SYMBOL}"

# ------------------------------------------------------------------------------
# 7. Colorized Output for Common Commands
# ------------------------------------------------------------------------------
if [ -x /usr/bin/dircolors ]; then
    if [ -r ~/.dircolors ]; then
        eval "$(dircolors -b ~/.dircolors)"
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

# ------------------------------------------------------------------------------
# 8. Aliases & Shortcuts (with OpenSUSE Package Management)
# ------------------------------------------------------------------------------
# Directory navigation
alias ll='ls -lah'
alias la='ls -A'
alias l='ls -CF'
alias ..='cd ..'
alias ...='cd ../..'
alias ....='cd ../../..'
alias .....='cd ../../../..'

# OpenSUSE System Management
alias update='sudo zypper refresh && sudo zypper update'
alias install='sudo zypper install'
alias remove='sudo zypper remove'
alias autoremove='sudo zypper remove -u'
alias search='sudo zypper search'

# Safety aliases for file operations
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
alias ports='ss -tulanp'   # Using 'ss' as a modern alternative to netstat
alias mem='free -h'
alias disk='df -h'

# Docker shortcuts
alias d='docker'
alias dc='docker-compose'
alias dps='docker ps'
alias di='docker images'

# Miscellaneous
alias sudo='sudo '   # Allow aliases to work with sudo
alias watch='watch '

# ------------------------------------------------------------------------------
# 9. Enhanced Functions
# ------------------------------------------------------------------------------
# Create and activate a Python virtual environment
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
    [ -f "requirements.txt" ] && pip install -r requirements.txt
    [ -f "requirements-dev.txt" ] && pip install -r requirements-dev.txt
}
alias venv='setup_venv'

# Universal archive extraction
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
         *) echo "Cannot extract '$1' with extract()"; return 1 ;;
    esac
}

# Create a directory and immediately cd into it
mkcd() {
    mkdir -p "$1" && cd "$1" || return 1
}

# Search for files by pattern
ff() {
    find . -type f -iname "*$1*"
}

# Search for directories by pattern
fd() {
    find . -type d -iname "*$1*"
}

# Quickly backup a file with a timestamped .bak
bak() {
    cp "$1" "${1}.bak.$(date +%Y%m%d_%H%M%S)"
}

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

# ------------------------------------------------------------------------------
# 10. Bash Completion
# ------------------------------------------------------------------------------
if ! shopt -oq posix; then
    if [ -f /usr/share/bash-completion/bash_completion ]; then
        . /usr/share/bash-completion/bash_completion
    elif [ -f /etc/bash_completion ]; then
        . /etc/bash_completion
    fi
fi

# ------------------------------------------------------------------------------
# 11. Local Customizations
# ------------------------------------------------------------------------------
# Source a local bashrc file if it exists
if [ -f ~/.bashrc.local ]; then
    source ~/.bashrc.local
fi

# Optional: Trap errors and display a Nord‑themed error message
# Uncomment the following line to enable error trapping:
# trap 'echo -e "${NORD11}Error on line ${LINENO}: ${BASH_COMMAND}${RESET}"' ERR

# ------------------------------------------------------------------------------
# 12. Source Additional Environment Settings
# ------------------------------------------------------------------------------
[ -f "$HOME/.local/bin/env" ] && source "$HOME/.local/bin/env"

# ------------------------------------------------------------------------------
# End of ~/.bashrc
# ------------------------------------------------------------------------------
