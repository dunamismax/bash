###############################################################################
# ~/.bashrc for FreeBSD - Enhanced Version
###############################################################################

# 0. Only run if we are in an interactive Bash shell
#    This prevents errors if another shell tries to source this file.
if [ -z "$BASH_VERSION" ] || [ -z "$PS1" ]; then
    return
fi

# 1. Environment Variables & Shell Options
# ------------------------------------------------------------------------------
# Prepend essential directories to PATH
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$HOME/.local/bin:$HOME/bin:$PATH"

# Enable useful Bash options (wrap in a check for shopt)
shopt -s checkwinsize histappend cmdhist autocd cdspell dirspell globstar nocaseglob extglob histverify 2>/dev/null || true

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
if [ "$TERM" = "xterm" ]; then
    export TERM="xterm-256color"
fi

# 2. Nord Color Scheme (Lighter Palette)
# ------------------------------------------------------------------------------
NORD4="\[\033[38;2;216;222;233m\]"
NORD5="\[\033[38;2;229;233;240m\]"
NORD6="\[\033[38;2;236;239;244m\]"
NORD7="\[\033[38;2;143;188;187m\]"
NORD8="\[\033[38;2;136;192;208m\]"
NORD9="\[\033[38;2;129;161;193m\]"
NORD10="\[\033[38;2;94;129;172m\]"
NORD11="\[\033[38;2;191;97;106m\]"
NORD12="\[\033[38;2;208;135;112m\]"
NORD13="\[\033[38;2;235;203;139m\]"
NORD14="\[\033[38;2;163;190;140m\]"
NORD15="\[\033[38;2;180;142;173m\]"
RESET="\[\e[0m\]"

# Customize LESS (pager) colors with the Nord palette
export LESS="-R -X -F -i -J --mouse"
export LESS_TERMCAP_mb=$'\e[38;2;191;97;106m'
export LESS_TERMCAP_md=$'\e[38;2;136;192;208m'
export LESS_TERMCAP_me=$'\e[0m'
export LESS_TERMCAP_so=$'\e[38;2;235;203;139m'
export LESS_TERMCAP_se=$'\e[0m'
export LESS_TERMCAP_us=$'\e[38;2;163;190;140m'
export LESS_TERMCAP_ue=$'\e[0m'

# 3. Enhanced History Settings
# ------------------------------------------------------------------------------
export HISTSIZE=1000000
export HISTFILESIZE=2000000
export HISTFILE="$HOME/.bash_history"
export HISTCONTROL="ignoreboth:erasedups"
export HISTTIMEFORMAT="%F %T "

# 4. System Information & Greeting
# ------------------------------------------------------------------------------
if command -v fastfetch >/dev/null 2>&1; then
    fastfetch
    echo
    echo
fi

# 5. Development Environment Setup
# ------------------------------------------------------------------------------
# Initialize Pyenv if installed
if [ -d "$HOME/.pyenv" ]; then
    export PYENV_ROOT="$HOME/.pyenv"
    export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init --path)"
    eval "$(pyenv init -)"
fi

# 6. Less (Pager) Setup
# ------------------------------------------------------------------------------
if command -v lesspipe >/dev/null 2>&1; then
    eval "$(SHELL=/bin/sh lesspipe)"
fi

# 7. Prompt Customization - Clean, Nord-themed Single-Line Prompt
# ------------------------------------------------------------------------------
USER_COLOR="${NORD7}"
HOST_COLOR="${NORD7}"
DIR_COLOR="${NORD9}"
PROMPT_ICON="${NORD10}> "
PS1="[${USER_COLOR}\u${RESET}@${HOST_COLOR}\h${RESET}] [${DIR_COLOR}\w${RESET}] ${PROMPT_ICON}${NORD6} "

# 8. Colorized Output for Common Commands
# ------------------------------------------------------------------------------
alias ls='ls -G'
alias ll='ls -lah'
alias la='ls -A'
alias l='ls -CF'

# For grep/diff (GNU vs. BSD)
if command -v ggrep >/dev/null 2>&1; then
    alias grep='ggrep --color=auto'
else
    alias grep='grep'
fi
if command -v gdiff >/dev/null 2>&1; then
    alias diff='gdiff --color=auto'
else
    alias diff='diff'
fi

# 9. Aliases & Shortcuts (FreeBSD Package Management & Common Operations)
# ------------------------------------------------------------------------------
alias ..='cd ..'
alias ...='cd ../..'
alias ....='cd ../../..'
alias .....='cd ../../../..'

# FreeBSD package management using pkg
alias update='sudo pkg update && sudo pkg upgrade -y'
alias install='sudo pkg install'
alias remove='sudo pkg delete'
alias autoremove='sudo pkg autoremove'
alias search='pkg search'

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

# Misc
alias h='history'
alias j='jobs -l'
alias path='echo -e ${PATH//:/\\n}'
alias now='date +"%T"'
alias nowdate='date +"%d-%m-%Y"'
alias ports='sockstat -4'
alias mem='top -o mem'
alias disk='df -h'
alias sudo='sudo '
alias watch='watch '

# Docker shortcuts (if Docker is installed)
alias d='docker'
alias dc='docker-compose'
alias dps='docker ps'
alias di='docker images'

# 10. Enhanced Functions
# ------------------------------------------------------------------------------
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

mkcd() {
    mkdir -p "$1" && cd "$1" || return 1
}

ff() {
    find . -type f -iname "*$1*"
}

fd() {
    find . -type d -iname "*$1*"
}

bak() {
    cp "$1" "${1}.bak.$(date +%Y%m%d_%H%M%S)"
}

mktempdir() {
    local tmpdir
    tmpdir=$(mktemp -d -t tmp.XXXXXX)
    echo "Created temporary directory: $tmpdir"
    cd "$tmpdir" || return
}

serve() {
    local port="${1:-8000}"
    echo "Serving HTTP on port ${port}..."
    python3 -m http.server "$port"
}

# 11. Bash Completion
# ------------------------------------------------------------------------------
if ! shopt -oq posix; then
    if [ -f /usr/local/etc/bash_completion ]; then
        . /usr/local/etc/bash_completion
    elif [ -f /etc/bash_completion ]; then
        . /etc/bash_completion
    fi
fi

# 12. Local Customizations
# ------------------------------------------------------------------------------
if [ -f ~/.bashrc.local ]; then
    source ~/.bashrc.local
fi

# Auto-load scripts in ~/.bashrc.d/
if [ -d "$HOME/.bashrc.d" ]; then
  for file in "$HOME"/.bashrc.d/*.sh; do
    [ -r "$file" ] && source "$file"
  done
fi

# 13. Source Additional Environment Settings
# ------------------------------------------------------------------------------
[ -f "$HOME/.local/bin/env" ] && source "$HOME/.local/bin/env"

# 14. Final PROMPT_COMMAND Consolidation
# ------------------------------------------------------------------------------
export PROMPT_COMMAND='history -a; echo "\n[$(date)] ${USER}@${HOSTNAME}:${PWD}\n" >> ~/.bash_sessions.log'

###############################################################################
# End of ~/.bashrc
###############################################################################
