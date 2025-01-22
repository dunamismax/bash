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

# ------------------------------------------------------------------------------
# 2. Environment variables
# ------------------------------------------------------------------------------
# Add your local bin directory to PATH.
export PATH="$PATH:$HOME/.local/bin"

# ------------------------------------------------------------------------------
# 3. pyenv initialization
# ------------------------------------------------------------------------------
# Adjust these lines according to your Python environment needs.
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"

if command -v pyenv 1>/dev/null 2>&1; then
    # Initialize pyenv so that it can manage your Python versions and virtualenvs.
    eval "$(pyenv init --path)"
    eval "$(pyenv init -)"
fi

# ------------------------------------------------------------------------------
# 4. History preferences
# ------------------------------------------------------------------------------
# Do not store duplicate lines or lines that start with a space in the history.
HISTCONTROL=ignoreboth

# Set history limits (number of lines in memory / on disk).
HISTSIZE=100000
HISTFILESIZE=200000

# Add timestamps to each command in history (for auditing).
HISTTIMEFORMAT="%F %T "

# ------------------------------------------------------------------------------
# 5. Less (pager) setup
# ------------------------------------------------------------------------------
# Make 'less' more friendly for non-text input files, see lesspipe(1).
[ -x /usr/bin/lesspipe ] && eval "$(SHELL=/bin/sh lesspipe)"

# ------------------------------------------------------------------------------
# 6. Bash prompt (PS1) with Nord color theme
# ------------------------------------------------------------------------------

# If terminal supports color, enable a colored prompt.
case "$TERM" in
    xterm-color|*-256color) color_prompt=yes;;
esac

# Uncomment the line below if you always want a color prompt (if supported).
force_color_prompt=yes

if [ -n "$force_color_prompt" ]; then
    if [ -x /usr/bin/tput ] && tput setaf 1 >&/dev/null; then
        # We have color support; assume it's compliant with Ecma-48 (ISO/IEC-6429).
        color_prompt=yes
    else
        color_prompt=
    fi
fi

# Choose a colored or plain prompt using Nord colors.
if [ "$color_prompt" = yes ]; then
    PS1='${ubuntu_chroot:+($ubuntu_chroot)}'\
'\[\033[38;2;136;192;208m\]\u@\h\[\033[00m\]:'\
'\[\033[38;2;94;129;172m\]\w\[\033[00m\]\$ '
else
    PS1='${ubuntu_chroot:+($ubuntu_chroot)}\u@\h:\w\$ '
fi
unset color_prompt force_color_prompt

# If this is an xterm or rxvt terminal, set the window title to user@host:dir.
case "$TERM" in
    xterm*|rxvt*)
        PS1="\[\e]0;${ubuntu_chroot:+($ubuntu_chroot)}\u@\h: \w\a\]$PS1"
        ;;
    *)
        ;;
esac

# ------------------------------------------------------------------------------
# 7. Color support for common commands
# ------------------------------------------------------------------------------
if [ -x /usr/bin/dircolors ]; then
    test -r ~/.dircolors && eval "$(dircolors -b ~/.dircolors)" || eval "$(dircolors -b)"
    alias ls='ls --color=auto'
    # alias dir='dir --color=auto'
    # alias vdir='vdir --color=auto'

    alias grep='grep --color=auto'
    alias fgrep='fgrep --color=auto'
    alias egrep='egrep --color=auto'
fi

# ------------------------------------------------------------------------------
# 8. Handy aliases
# ------------------------------------------------------------------------------
# Basic ls aliases
alias ll='ls -alF'
alias la='ls -A'
alias l='ls -CF'

# Launch ranger file manager
alias r='ranger'

# Alert alias for long running commands (use: sleep 10; alert)
alias alert='notify-send --urgency=low -i "$([ $? = 0 ] && echo terminal || echo error)" \
"$(history|tail -n1|sed -e '\''s/^\s*[0-9]\+\s*//;s/[;&|]\s*alert$//'\'')"'

# ------------------------------------------------------------------------------
# 9. Python virtual environment functions and aliases
# ------------------------------------------------------------------------------
# Alias to quickly set up a new Python virtual environment
alias venv='setup_venv'
# Alias to quickly re-enable an existing Python virtual environment
alias v='enable_venv'

# Function to set up a new Python virtual environment in the current directory
setup_venv() {
    # If there's already a venv active, deactivate it first
    if type deactivate &>/dev/null; then
        echo "Deactivating current virtual environment..."
        deactivate
    fi

    echo "Creating a new virtual environment in $(pwd)/.venv..."
    python -m venv .venv

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

# Function to re-enable an existing Python virtual environment in the current directory
enable_venv() {
    # If there's already a venv active, deactivate it first
    if type deactivate &>/dev/null; then
        echo "Deactivating current virtual environment..."
        deactivate
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
# 10. Load user-defined aliases from ~/.bash_aliases (if it exists)
# ------------------------------------------------------------------------------
if [ -f ~/.bash_aliases ]; then
    . ~/.bash_aliases
fi

# ------------------------------------------------------------------------------
# 11. Bash completion
# ------------------------------------------------------------------------------
# Enable programmable completion features if not in POSIX mode.
# (Examples: git completion, docker completion, etc.)
if ! shopt -oq posix; then
    if [ -f /usr/share/bash-completion/bash_completion ]; then
        . /usr/share/bash-completion/bash_completion
    elif [ -f /etc/bash_completion ]; then
        . /etc/bash_completion
    fi
fi

# ------------------------------------------------------------------------------
# End of ~/.bashrc
# ------------------------------------------------------------------------------