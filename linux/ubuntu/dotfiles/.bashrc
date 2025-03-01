###############################################################################
# ~/.bashrc – Enhanced Ubuntu Bash Configuration with Nord Theme
###############################################################################

# 0. Exit if not running in an interactive shell
[[ $- != *i* ]] && return

# 1. Environment Variables, PATH, and Shell Options
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

# Wayland settings
export QT_QPA_PLATFORM=wayland
export XDG_SESSION_TYPE=wayland

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

# Locale and Terminal settings
export LANG="en_US.UTF-8"
export LC_ALL="en_US.UTF-8"
export TZ="America/New_York"
[[ "$TERM" == "xterm" ]] && export TERM="xterm-256color"

# 2. Nord Color Palette – Official Colors
# ------------------------------------------------------------------------------
export NORD0="\[\033[38;2;46;52;64m\]"    # #2E3440
export NORD1="\[\033[38;2;59;67;82m\]"    # #3B4252
export NORD2="\[\033[38;2;67;76;94m\]"    # #434C5E
export NORD3="\[\033[38;2;76;86;106m\]"   # #4C566A
export NORD4="\[\033[38;2;216;222;233m\]"  # #D8DEE9
export NORD5="\[\033[38;2;229;233;240m\]"  # #E5E9F0
export NORD6="\[\033[38;2;236;239;244m\]"  # #ECEFF4
export NORD7="\[\033[38;2;143;188;187m\]"  # #8FBCBB
export NORD8="\[\033[38;2;136;192;208m\]"  # #88C0D0
export NORD9="\[\033[38;2;129;161;193m\]"  # #81A1C1
export NORD10="\[\033[38;2;94;129;172m\]"  # #5E81AC
export NORD11="\[\033[38;2;191;97;106m\]"  # #BF616A
export NORD12="\[\033[38;2;208;135;112m\]" # #D08770
export NORD13="\[\033[38;2;235;203;139m\]" # #EBCB8B
export NORD14="\[\033[38;2;163;190;140m\]" # #A3BE8C
export NORD15="\[\033[38;2;180;142;173m\]" # #B48EAD
export RESET="\[\e[0m\]"

# 3. LESS and MAN Colors – Consistent with Nord
# ------------------------------------------------------------------------------
export LESS="-R -X -F -i -J --mouse"
export LESS_TERMCAP_mb=$'\e[38;2;191;97;106m'   # Bold red (Nord11)
export LESS_TERMCAP_md=$'\e[38;2;136;192;208m'   # Bold blue (Nord8)
export LESS_TERMCAP_me=$'\e[0m'
export LESS_TERMCAP_so=$'\e[38;2;235;203;139m'   # Standout (Nord13)
export LESS_TERMCAP_se=$'\e[0m'
export LESS_TERMCAP_us=$'\e[38;2;163;190;140m'   # Underline (Nord14)
export LESS_TERMCAP_ue=$'\e[0m'

# 4. Bash History and Window Settings
# ------------------------------------------------------------------------------
export HISTSIZE=10000
export HISTFILESIZE=20000
export HISTCONTROL="ignoreboth"
shopt -s histappend
PROMPT_COMMAND='history -a'
shopt -s checkwinsize

# 5. Development Environment (pyenv support)
# ------------------------------------------------------------------------------
if [ -d "$HOME/.pyenv" ]; then
    export PYENV_ROOT="$HOME/.pyenv"
    export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init --path)"
    eval "$(pyenv init -)"
fi

# 6. Terminal Pager Setup
# ------------------------------------------------------------------------------
if command -v lesspipe >/dev/null 2>&1; then
    eval "$(SHELL=/bin/sh lesspipe)"
fi

# 7. Prompt Customization (without Git integration)
# ------------------------------------------------------------------------------
# Set a dynamic terminal title and a Nord-themed prompt:
case "$TERM" in
    xterm*|rxvt*)
        PROMPT_TITLE="\[\e]0;\u@\h: \w\a\]"
        ;;
    *)
        PROMPT_TITLE=""
        ;;
esac

# Example prompt: [user@host] [cwd] > 
PS1="${PROMPT_TITLE}${NORD7}\u@\h${RESET} ${NORD9}\w${RESET} ${NORD10}>\$ ${RESET}"

# 8. Aliases and Shortcuts (Non-Git)
# ------------------------------------------------------------------------------
alias ls='ls --color=auto'
alias ll='ls -alF'
alias la='ls -A'
alias l='ls -CF'
alias grep='grep --color=auto'

# Navigation aliases
alias ..='cd ..'
alias ...='cd ../..'
alias ....='cd ../../..'
alias .....='cd ../../../..'

# Package Management (using Nala if installed)
alias apt='nala'
alias apt-get='nala'
alias apt-cache='nala'
alias update='sudo nala update && sudo nala upgrade -y'
alias install='sudo nala install'
alias remove='sudo nala remove'
alias autoremove='sudo nala autoremove'
alias search='nala search'

# Safety aliases
alias rm='rm -i'
alias cp='cp -i'
alias mv='mv -i'
alias mkdir='mkdir -p'

# Miscellaneous aliases
alias h='history'
alias path='echo -e ${PATH//:/\\n}'
alias now='date +"%T"'
alias nowdate='date +"%d-%m-%Y"'
alias ports='ss -tulwn'
alias mem='top'
alias disk='df -h'
alias watch='watch'
alias cls='clear'

# 9. Functions
# ------------------------------------------------------------------------------
# Create directory and cd into it
mkcd() {
    mkdir -p "$1" && cd "$1" || return 1
}

# Universal archive extractor function
extract() {
    if [ -z "$1" ]; then
        echo "Usage: extract <archive-file>"
        return 1
    elif [ ! -f "$1" ]; then
        echo "File '$1' not found."
        return 1
    fi
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
        *) echo "Cannot extract '$1' - unknown format" ; return 1 ;;
    esac
}

# 10. Load Local Customizations
# ------------------------------------------------------------------------------
if [ -f "$HOME/.bashrc.local" ]; then
    . "$HOME/.bashrc.local"
fi

# Auto-load additional scripts from ~/.bashrc.d/
if [ -d "$HOME/.bashrc.d" ]; then
    for file in "$HOME"/.bashrc.d/*.sh; do
        [ -r "$file" ] && . "$file"
    done
fi

# 11. Final PROMPT_COMMAND Consolidation (Logging Sessions)
# ------------------------------------------------------------------------------
export PROMPT_COMMAND='history -a; echo -e "\n[$(date)] ${USER}@${HOSTNAME}:${PWD}\n" >> ~/.bash_sessions.log'

# -------------------------------------------------------------------------------
# Override python command to use sudo with the pyenv Python interpreter
# This alias allows you to run "python script.py" and have it execute:
#   sudo $(pyenv which python) script.py
# -------------------------------------------------------------------------------
python() {
    sudo "$(pyenv which python)" "$@"
}

###############################################################################
# End of ~/.bashrc
###############################################################################
