# ~/.bashrc: executed by bash(1) for non-login shells.
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
# FreeBSD specific PATH additions
export PATH="/usr/local/bin:/usr/local/sbin:$PATH:$HOME/.local/bin"
export MANPATH="/usr/local/man:$MANPATH"

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
# 3. History preferences
# ------------------------------------------------------------------------------
HISTCONTROL=ignoreboth
HISTSIZE=100000
HISTFILESIZE=200000
HISTTIMEFORMAT="%F %T "

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

# Launch ranger file manager (if installed)
if command -v ranger >/dev/null 2>&1; then
    alias r='ranger'
fi

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
# 9. Load user-defined aliases
# ------------------------------------------------------------------------------
if [ -f ~/.bash_aliases ]; then
    . ~/.bash_aliases
fi

# ------------------------------------------------------------------------------
# 10. Bash completion (FreeBSD specific)
# ------------------------------------------------------------------------------
if [ -f /usr/local/share/bash-completion/bash_completion.sh ]; then
    . /usr/local/share/bash-completion/bash_completion.sh
fi

# ------------------------------------------------------------------------------
# 11. Editor configuration
# ------------------------------------------------------------------------------
export EDITOR=/usr/local/bin/vim
export VISUAL=/usr/local/bin/vim

# ------------------------------------------------------------------------------
# 12. Local customizations
# ------------------------------------------------------------------------------
# Source local customizations if they exist
if [ -f ~/.bashrc.local ]; then
    . ~/.bashrc.local
fi

# ------------------------------------------------------------------------------
# End of ~/.bashrc
# ------------------------------------------------------------------------------