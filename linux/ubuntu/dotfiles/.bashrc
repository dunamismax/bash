###############################################################################
# ~/.bashrc – Enhanced Ubuntu Bash Configuration
###############################################################################

# 0. Exit if not an interactive shell
[[ $- != *i* ]] && return

# 1. Environment Variables & Shell Options
# ------------------------------------------------------------------------------
# Prepend essential directories to PATH
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$HOME/.local/bin:$HOME/bin:$PATH"

# Enable useful Bash options
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
else
    export EDITOR="nano"
    export VISUAL="nano"
fi
export PAGER="less"

# Locale and Timezone
export LANG="en_US.UTF-8"
export LC_ALL="en_US.UTF-8"
export TZ="America/New_York"

# Force 256-color mode for xterm
[[ "$TERM" == "xterm" ]] && export TERM="xterm-256color"

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
    echo -e "\n"
fi

# 5. Development Environment Setup
# ------------------------------------------------------------------------------
# Initialize pyenv if installed
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

# 7. Prompt Customization – Clean, Nord-themed Prompt with Git Branch
# ------------------------------------------------------------------------------
# Function to extract current Git branch (if any)
parse_git_branch() {
    git rev-parse --abbrev-ref HEAD 2>/dev/null | sed "s/^/ (\e[38;2;136;192;208m/; s/$/\e[0m)/"
}
# Define prompt colors
USER_COLOR="${NORD7}"
HOST_COLOR="${NORD7}"
DIR_COLOR="${NORD9}"
PROMPT_ICON="${NORD10}> "
export PS1="[\u@\h] [${DIR_COLOR}\w${RESET}]\$(parse_git_branch) ${PROMPT_ICON}${NORD6} "

# 8. Colorized Output for Common Commands & Aliases
# ------------------------------------------------------------------------------
alias ls='ls --color=auto'
alias ll='ls -lah'
alias la='ls -A'
alias l='ls -CF'

# For grep/diff
alias grep='grep --color=auto'
# If colordiff is installed, you might use: alias diff='colordiff'

# 9. Aliases & Shortcuts (Ubuntu Package Management & Common Operations)
# ------------------------------------------------------------------------------
alias ..='cd ..'
alias ...='cd ../..'
alias ....='cd ../../..'
alias .....='cd ../../../..'

# Ubuntu package management via apt
alias update='sudo apt update && sudo apt upgrade -y'
alias install='sudo apt install'
alias remove='sudo apt remove'
alias autoremove='sudo apt autoremove'
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

# Miscellaneous aliases
alias h='history'
alias j='jobs -l'
alias path='echo -e ${PATH//:/\\n}'
alias now='date +"%T"'
alias nowdate='date +"%d-%m-%Y"'
alias ports='ss -tulwn'
alias mem='top'
alias disk='df -h'
alias watch='watch'

# Docker shortcuts (if installed)
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
    elif [ ! -f "$1" ]; then
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

mkcd() { mkdir -p "$1" && cd "$1" || return 1; }
ff() { find . -type f -iname "*$1*"; }
fd() { find . -type d -iname "*$1*"; }
bak() { cp "$1" "${1}.bak.$(date +%Y%m%d_%H%M%S)"; }
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
    if [ -f /usr/share/bash-completion/bash_completion ]; then
        . /usr/share/bash-completion/bash_completion
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
export PROMPT_COMMAND='history -a; echo -e "\n[$(date)] ${USER}@${HOSTNAME}:${PWD}\n" >> ~/.bash_sessions.log'

###############################################################################
# End of ~/.bashrc
###############################################################################