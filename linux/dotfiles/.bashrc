###############################################################################
# ~/.bashrc
#
# Executed by bash(1) for interactive non-login shells.
# This configuration sets up environment variables, shell options,
# a customized prompt with Nord colors, aliases, functions, and more.
###############################################################################

#################################
# 0. Early Exit for Non-Interactive Shells
#################################
case $- in
    *i*) ;;  # Interactive shell: do nothing
      *) return;;
esac

#################################
# 1. Environment Variables & PATH
#################################
# Extend PATH with essential system directories and user binaries.
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$HOME/.local/bin:/usr/local/go/bin:$HOME/bin:$PATH"

# Set XDG Base Directories (freedesktop.org standard)
export XDG_CONFIG_HOME="$HOME/.config"
export XDG_DATA_HOME="$HOME/.local/share"
export XDG_CACHE_HOME="$HOME/.cache"
export XDG_STATE_HOME="$HOME/.local/state"

# Locale, Timezone, and Terminal Type
export LANG="en_US.UTF-8"
export LC_ALL="en_US.UTF-8"
export TZ="America/New_York"
[[ "$TERM" == "xterm" ]] && export TERM="xterm-256color"

# Editor & Pager Setup: Prefer nvim if available, fallback to vim.
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

#################################
# 2. Shell Options & History Control
#################################
# Enable useful Bash options for enhanced usability.
shopt -s checkwinsize   # Update window size after each command.
shopt -s histappend     # Append to history instead of overwriting.
shopt -s cmdhist        # Save multi-line commands as a single entry.
shopt -s autocd         # Change to a directory by typing its name.
shopt -s cdspell        # Autocorrect minor typos in cd commands.
shopt -s dirspell       # Autocorrect directory names during completion.
shopt -s globstar       # Enable recursive globbing (e.g., **).
shopt -s nocaseglob     # Case-insensitive pathname expansion.
shopt -s extglob        # Enable extended globbing.
shopt -s histverify     # Allow editing of history substitutions.

# Enhanced History Configuration
export HISTSIZE=1000000
export HISTFILESIZE=2000000
export HISTFILE="$HOME/.bash_history"
export HISTCONTROL="ignoreboth:erasedups"
export HISTTIMEFORMAT="%F %T "
export HISTIGNORE="ls:ll:cd:pwd:bg:fg:history:clear:exit"
export PROMPT_COMMAND='history -a'

#################################
# 3. LESS (Pager) Configuration
#################################
export LESS="-R -X -F -i -J --mouse"
export LESS_TERMCAP_mb=$'\e[1;31m'     # Begin blink (red)
export LESS_TERMCAP_md=$'\e[1;36m'     # Begin bold (cyan)
export LESS_TERMCAP_me=$'\e[0m'        # End bold/blink
export LESS_TERMCAP_so=$'\e[01;44;33m' # Begin standout (yellow on blue)
export LESS_TERMCAP_se=$'\e[0m'        # End standout
export LESS_TERMCAP_us=$'\e[1;32m'     # Begin underline (green)
export LESS_TERMCAP_ue=$'\e[0m'        # End underline

#################################
# 4. Nord Color Scheme (ANSI Sequences)
#################################
# These variables are used for a consistent Nord-themed prompt.
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
RESET="\[\e[0m\]"

#################################
# 5. System Information & Greeting
#################################
# Display system info using neofetch or screenfetch (if installed).
if command -v neofetch >/dev/null 2>&1; then
    neofetch
elif command -v screenfetch >/dev/null 2>&1; then
    screenfetch
fi

#################################
# 6. Development Environment Setup
#################################
# Initialize pyenv if it exists.
if [ -d "$HOME/.pyenv" ]; then
    export PYENV_ROOT="$HOME/.pyenv"
    export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init --path)"
    eval "$(pyenv init -)"
fi

#################################
# 7. Lesspipe Setup for Ubuntu
#################################
# Enable lesspipe for enhanced file viewing if available.
[ -x /usr/bin/lesspipe ] && eval "$(SHELL=/bin/sh lesspipe)"

#################################
# 8. Customized Prompt (PS1)
#################################
# Build a simple single-line prompt using Nord colors.
USERNAME="\[\033[38;2;143;188;187m\]"   # NORD7 (Frost - turquoise)
HOSTNAME="\[\033[38;2;143;188;187m\]"   # NORD7 (Frost - turquoise)
DIR_COLOR="\[\033[38;2;129;161;193m\]"  # NORD9 (Frost - blue)
DELIM="\[\033[38;2;216;222;233m\]"      # NORD4 (Snow Storm - darkest)
PS1="${USERNAME}\u${DELIM}@${HOSTNAME}\h${DELIM}:${DIR_COLOR}\w${DELIM} ❯${RESET} "

#################################
# 9. Color Support for Common Commands
#################################
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

#################################
# 10. Enhanced Aliases
#################################
# Navigation shortcuts.
alias ll='ls -lah'
alias la='ls -A'
alias l='ls -CF'
alias ..='cd ..'
alias ...='cd ../..'
alias ....='cd ../../..'
alias .....='cd ../../../..'

# System management.
alias update='sudo apt update && sudo apt upgrade'
alias install='sudo apt install'
alias remove='sudo apt remove'
alias purge='sudo apt purge'
alias autoremove='sudo apt autoremove'

# Safety enhancements for file operations.
alias rm='rm -i'
alias cp='cp -i'
alias mv='mv -i'
alias mkdir='mkdir -p'

# Git shortcuts.
alias gs='git status'
alias ga='git add'
alias gc='git commit'
alias gp='git push'
alias gl='git pull'
alias gd='git diff'
alias glog='git log --oneline --graph --decorate'

# Miscellaneous utilities.
alias h='history'
alias j='jobs -l'
alias path='echo -e ${PATH//:/\\n}'
alias now='date +"%T"'
alias nowdate='date +"%d-%m-%Y"'
alias ports='netstat -tulanp'
alias mem='free -h'
alias disk='df -h'

# Docker shortcuts.
alias d='docker'
alias dc='docker-compose'
alias dps='docker ps'
alias di='docker images'

# User convenience.
alias venv='setup_venv'
alias sudo='sudo '
alias watch='watch '

#################################
# 11. Custom Functions
#################################

# Create and activate a Python virtual environment.
setup_venv() {
    local venv_name="${1:-.venv}"
    # Deactivate any existing virtual environment.
    type deactivate &>/dev/null && deactivate

    if [ ! -d "$venv_name" ]; then
        echo "Creating virtual environment in '$venv_name'..."
        python3 -m venv "$venv_name"
    fi
    source "$venv_name/bin/activate"

    # Automatically install dependencies if requirements files are found.
    [ -f "requirements.txt" ] && pip install -r requirements.txt
    [ -f "requirements-dev.txt" ] && pip install -r requirements-dev.txt
}

# Extract various archive types.
extract() {
    if [ -z "$1" ]; then
        echo "Usage: extract <archive>"
        return 1
    fi
    if [ ! -f "$1" ]; then
        echo "Error: '$1' does not exist."
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
            echo "Error: '$1' cannot be extracted."
            return 1
            ;;
    esac
}

# Create a directory and change into it.
mkcd() {
    mkdir -p "$1" && cd "$1" || return 1
}

# Find files by a case-insensitive pattern.
ff() {
    find . -type f -iname "*$1*"
}

# Find directories by a case-insensitive pattern.
fd() {
    find . -type d -iname "*$1*"
}

# Backup a file by copying it with a timestamp appended.
bak() {
    cp "$1" "${1}.bak.$(date +%Y%m%d_%H%M%S)"
}

#################################
# 12. Bash Completion
#################################
if ! shopt -oq posix; then
    if [ -f /usr/share/bash-completion/bash_completion ]; then
        . /usr/share/bash-completion/bash_completion
    elif [ -f /etc/bash_completion ]; then
        . /etc/bash_completion
    fi
fi

#################################
# 13. Local Customizations
#################################
# Source additional customizations if ~/.bashrc.local exists.
if [ -f ~/.bashrc.local ]; then
    source ~/.bashrc.local
fi

#################################
# 14. Final Environment Setup
#################################
# Source extra environment settings, if available.
. "$HOME/.local/share/../bin/env"

###############################################################################
# End of ~/.bashrc
###############################################################################