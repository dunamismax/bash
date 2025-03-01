###############################################################################
# ~/.bashrc – Enhanced Ubuntu Bash Configuration with Nala Aliases and Nord Theme
###############################################################################

# 0. Exit if not running in an interactive shell
[[ $- != *i* ]] && return

# 1. Environment Variables, PATH, and Shell Options
# ------------------------------------------------------------------------------
# Prepend essential directories to PATH
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$HOME/.local/bin:$HOME/bin:$PATH"

# Enable useful Bash options
shopt -s checkwinsize histappend cmdhist autocd cdspell dirspell globstar nocaseglob extglob histverify 2>/dev/null || true

# XDG Base Directories (for configuration, data, cache, and state)
export XDG_CONFIG_HOME="$HOME/.config"
export XDG_DATA_HOME="$HOME/.local/share"
export XDG_CACHE_HOME="$HOME/.cache"
export XDG_STATE_HOME="$HOME/.local/state"

# Wayland settings
export QT_QPA_PLATFORM=wayland
export XDG_SESSION_TYPE=wayland

# Set default editor and pager (prefer nvim > vim > nano)
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

# Locale and Terminal settings
export LANG="en_US.UTF-8"
export LC_ALL="en_US.UTF-8"
export TZ="America/New_York"
[[ "$TERM" == "xterm" ]] && export TERM="xterm-256color"

# 2. Nord Color Scheme (Lighter Palette)
# ------------------------------------------------------------------------------
NORD4="\[\033[38;2;216;222;233m\]"    # #D8DEE9
NORD5="\[\033[38;2;229;233;240m\]"    # #E5E9F0
NORD6="\[\033[38;2;236;239;244m\]"    # #ECEFF4
NORD7="\[\033[38;2;143;188;187m\]"    # #8FBCBB
NORD8="\[\033[38;2;136;192;208m\]"    # #88C0D0
NORD9="\[\033[38;2;129;161;193m\]"    # #81A1C1
NORD10="\[\033[38;2;94;129;172m\]"    # #5E81AC
NORD11="\[\033[38;2;191;97;106m\]"    # #BF616A
NORD12="\[\033[38;2;208;135;112m\]"   # #D08770
NORD13="\[\033[38;2;235;203;139m\]"   # #EBCB8B
NORD14="\[\033[38;2;163;190;140m\]"   # #A3BE8C
NORD15="\[\033[38;2;180;142;173m\]"   # #B48EAD
RESET="\[\e[0m\]"

# Customize LESS colors with the Nord palette
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
shopt -s histappend
PROMPT_COMMAND='history -a'

# 4. System Information & Greeting
# ------------------------------------------------------------------------------
if command -v fastfetch >/dev/null 2>&1; then
    echo -e "\n"
    fastfetch
    echo -e "\n"
fi

# 5. Development Environment Setup
# ------------------------------------------------------------------------------
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

# 7. Prompt Customization – (Do Not Modify the PS1 Prompt)
# ------------------------------------------------------------------------------
# Using the exact PS1 from your provided file:
export PS1="[${NORD7}\u${RESET}@${NORD7}\h${RESET}] [${NORD9}\w${RESET}] ${NORD10}> ${NORD6} "

# 8. Colorized Output and Common Command Aliases
# ------------------------------------------------------------------------------
alias ls='ls --color=auto'
alias ll='ls -lah'
alias la='ls -A'
alias l='ls -CF'
alias grep='grep --color=auto'
# Uncomment the following if colordiff is installed:
# alias diff='colordiff'

# 9. Navigation and Package Management Aliases
# ------------------------------------------------------------------------------
alias ..='cd ..'
alias ...='cd ../..'
alias ....='cd ../../..'
alias .....='cd ../../../..'

# Package Management Aliases using Nala (if installed)
alias apt='nala'
alias apt-get='nala'
alias apt-cache='nala'
alias update='sudo nala update && sudo nala upgrade -y'
alias install='sudo nala install'
alias remove='sudo nala remove'
alias autoremove='sudo nala autoremove'
alias search='nala search'

# Safety Aliases
alias rm='rm -i'
alias cp='cp -i'
alias mv='mv -i'
alias mkdir='mkdir -p'

# 10. Git Command Shortcuts
# ------------------------------------------------------------------------------
alias gs='git status'
alias ga='git add'
alias gc='git commit'
alias gp='git push'
alias gl='git pull'
alias gd='git diff'
alias glog='git log --oneline --graph --decorate'

# 11. Miscellaneous Aliases for Common Tasks
# ------------------------------------------------------------------------------
alias h='history'
alias j='jobs -l'
alias path='echo -e ${PATH//:/\\n}'
alias now='date +"%T"'
alias nowdate='date +"%d-%m-%Y"'
alias ports='ss -tulwn'
alias mem='top'
alias disk='df -h'
alias watch='watch'

# Docker Shortcuts
alias d='docker'
alias dc='docker-compose'
alias dps='docker ps'
alias di='docker images'

# 12. Functions and Utility Scripts
# ------------------------------------------------------------------------------
# Virtual Environment Setup
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

# Universal extract function for archives
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

# Additional helper functions
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

# 13. Bash Completion
# ------------------------------------------------------------------------------
if ! shopt -oq posix; then
    if [ -f /usr/share/bash-completion/bash_completion ]; then
        . /usr/share/bash-completion/bash_completion
    elif [ -f /etc/bash_completion ]; then
        . /etc/bash_completion
    fi
fi

# 14. Local Customizations
# ------------------------------------------------------------------------------
[ -f "$HOME/.bashrc.local" ] && source "$HOME/.bashrc.local"

# Auto-load additional scripts from ~/.bashrc.d/
if [ -d "$HOME/.bashrc.d" ]; then
    for file in "$HOME"/.bashrc.d/*.sh; do
        [ -r "$file" ] && source "$file"
    done
fi

# 15. Source Additional Environment Settings
# ------------------------------------------------------------------------------
[ -f "$HOME/.local/bin/env" ] && source "$HOME/.local/bin/env"

# 16. Final PROMPT_COMMAND Consolidation (Logging Sessions)
# ------------------------------------------------------------------------------
export PROMPT_COMMAND='history -a; echo -e "\n[$(date)] ${USER}@${HOSTNAME}:${PWD}\n" >> ~/.bash_sessions.log'

# -------------------------------------------------------------------------------
# Override python command to use sudo with the pyenv Python interpreter
# This allows you to run "python script.py" and have it execute:
#   sudo $(pyenv which python) script.py
# -------------------------------------------------------------------------------
python() {
    sudo "$(pyenv which python)" "$@"
}

###############################################################################
# End of ~/.bashrc
###############################################################################
