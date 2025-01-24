# ------------------------------------------------------------------------------
#        ______                  ______
#        ___  /_ ______ ____________  /_ _______________
#        __  __ \_  __ `/__  ___/__  __ \__  ___/_  ___/
#    ___ _  /_/ // /_/ / _(__  ) _  / / /_  /    / /__
#    _(_)/_.___/ \__,_/  /____/  /_/ /_/ /_/     \___/
#
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# 0. Early return if not running interactively
# ------------------------------------------------------------------------------
case $- in
    *i*) ;;
      *) return;;
esac

# 1. Environment variables
# ------------------------------------------------------------------------------

# Nord color scheme
export NORD0="#2E3440"   # Polar Night (darkest)
export NORD1="#3B4252"   # Polar Night
export NORD2="#434C5E"   # Polar Night
export NORD3="#4C566A"   # Polar Night (lightest)
export NORD4="#D8DEE9"   # Snow Storm (darkest)
export NORD5="#E5E9F0"   # Snow Storm
export NORD6="#ECEFF4"   # Snow Storm (lightest)
export NORD7="#8FBCBB"   # Frost (turquoise)
export NORD8="#88C0D0"   # Frost (light blue)
export NORD9="#81A1C1"   # Frost (blue)
export NORD10="#5E81AC"  # Frost (dark blue)
export NORD11="#BF616A"  # Aurora (red)
export NORD12="#D08770"  # Aurora (orange)
export NORD13="#EBCB8B"  # Aurora (yellow)
export NORD14="#A3BE8C"  # Aurora (green)
export NORD15="#B48EAD"  # Aurora (purple)

# Reset color code
RESET='\[\e[0m\]'

# Set terminal colors to Nord theme
if [ "$TERM" = "xterm-256color" ] || [ "$TERM" = "screen-256color" ]; then
    printf '\e]4;0;%s\e\\' "$NORD0"   # Color 0 (black)
    printf '\e]4;1;%s\e\\' "$NORD11"  # Color 1 (red)
    printf '\e]4;2;%s\e\\' "$NORD14"  # Color 2 (green)
    printf '\e]4;3;%s\e\\' "$NORD13"  # Color 3 (yellow)
    printf '\e]4;4;%s\e\\' "$NORD10"  # Color 4 (blue)
    printf '\e]4;5;%s\e\\' "$NORD15"  # Color 5 (purple)
    printf '\e]4;6;%s\e\\' "$NORD7"   # Color 6 (cyan)
    printf '\e]4;7;%s\e\\' "$NORD6"   # Color 7 (white)
    printf '\e]4;8;%s\e\\' "$NORD4"   # Color 8 (bright black)
    printf '\e]4;9;%s\e\\' "$NORD11"  # Color 9 (bright red)
    printf '\e]4;10;%s\e\\' "$NORD14" # Color 10 (bright green)
    printf '\e]4;11;%s\e\\' "$NORD13" # Color 11 (bright yellow)
    printf '\e]4;12;%s\e\\' "$NORD9"  # Color 12 (bright blue)
    printf '\e]4;13;%s\e\\' "$NORD15" # Color 13 (bright purple)
    printf '\e]4;14;%s\e\\' "$NORD7"  # Color 14 (bright cyan)
    printf '\e]4;15;%s\e\\' "$NORD6"  # Color 15 (bright white)
fi

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
# 2. Greeting
# ------------------------------------------------------------------------------
neofetch
echo "-----------------------------------"
echo "Welcome, $USER!"
echo "-----------------------------------"

# ------------------------------------------------------------------------------
# 3. pyenv initialization
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
# 5. Set PS1 with Nord colors (no Git integration)
# ------------------------------------------------------------------------------
if [ "$color_prompt" = yes ]; then
    PS1="\[${NORD7}\]\u\[${RESET}\]@\[${NORD8}\]\h\[${RESET}\]:\[${NORD9}\]\w\[${RESET}\]"
    PS1+="\n\[${NORD13}\][\t]\[${RESET}\] "
    PS1+="\$(if [[ \$? -eq 0 ]]; then echo '\[${NORD12}\]'; else echo '\[${NORD11}\]'; fi)\$\[${RESET}\] "
else
    PS1='\u@\h:\w\$ '
fi
unset color_prompt force_color_prompt

# ------------------------------------------------------------------------------
# 6. Color support for FreeBSD ls and other commands
# ------------------------------------------------------------------------------
# FreeBSD ls colors with Nord theme
export CLICOLOR=1
export LS_COLORS="rs=0:di=01;34:ln=01;36:mh=00:pi=40;33:so=01;35:do=01;35:bd=40;33;01:cd=40;33;01:or=40;31;01:mi=00:su=37;41:sg=30;43:ca=30;41:tw=30;42:ow=34;42:st=37;44:ex=01;32:*.tar=01;31:*.tgz=01;31:*.arc=01;31:*.arj=01;31:*.taz=01;31:*.lha=01;31:*.lz4=01;31:*.lzh=01;31:*.lzma=01;31:*.tlz=01;31:*.txz=01;31:*.tzo=01;31:*.t7z=01;31:*.zip=01;31:*.z=01;31:*.Z=01;31:*.dz=01;31:*.gz=01;31:*.lrz=01;31:*.lz=01;31:*.lzo=01;31:*.xz=01;31:*.zst=01;31:*.tzst=01;31:*.bz2=01;31:*.bz=01;31:*.tbz=01;31:*.tbz2=01;31:*.tz=01;31:*.deb=01;31:*.rpm=01;31:*.jar=01;31:*.war=01;31:*.ear=01;31:*.sar=01;31:*.rar=01;31:*.alz=01;31:*.ace=01;31:*.zoo=01;31:*.cpio=01;31:*.7z=01;31:*.rz=01;31:*.cab=01;31:*.wim=01;31:*.swm=01;31:*.dwm=01;31:*.esd=01;31:*.jpg=01;35:*.jpeg=01;35:*.mjpg=01;35:*.mjpeg=01;35:*.gif=01;35:*.bmp=01;35:*.pbm=01;35:*.pgm=01;35:*.ppm=01;35:*.tga=01;35:*.xbm=01;35:*.xpm=01;35:*.tif=01;35:*.tiff=01;35:*.png=01;35:*.svg=01;35:*.svgz=01;35:*.mng=01;35:*.pcx=01;35:*.mov=01;35:*.mpg=01;35:*.mpeg=01;35:*.m2v=01;35:*.mkv=01;35:*.webm=01;35:*.ogm=01;35:*.mp4=01;35:*.m4v=01;35:*.mp4v=01;35:*.vob=01;35:*.qt=01;35:*.nuv=01;35:*.wmv=01;35:*.asf=01;35:*.rm=01;35:*.rmvb=01;35:*.flc=01;35:*.avi=01;35:*.fli=01;35:*.flv=01;35:*.gl=01;35:*.dl=01;35:*.xcf=01;35:*.xwd=01;35:*.yuv=01;35:*.cgm=01;35:*.emf=01;35:*.ogv=01;35:*.ogx=01;35:*.aac=00;36:*.au=00;36:*.flac=00;36:*.m4a=00;36:*.mid=00;36:*.midi=00;36:*.mka=00;36:*.mp3=00;36:*.mpc=00;36:*.ogg=00;36:*.ra=00;36:*.wav=00;36:*.oga=00;36:*.opus=00;36:*.spx=00;36:*.xspf=00;36"

# Colorized grep with Nord theme
export GREP_COLORS="\
ms=01;31:\           # Matched text (NORD11, Aurora red)
mc=01;31:\           # Context-matched text (NORD11, Aurora red)
sl=:\                # Unmatched lines (default)
cx=:\                # Context lines (default)
fn=35:\              # Filename (NORD15, Aurora purple)
ln=32:\              # Line numbers (NORD14, Aurora green)
bn=32:\              # Byte offsets (NORD14, Aurora green)
se=36"               # Separators (NORD7, Frost turquoise)

# Man Pages with Nord Colors
export MANPAGER="less -s -M +Gg"
export LESS_TERMCAP_mb=$'\e[1;31m'     # begin blink (NORD11, Aurora red)
export LESS_TERMCAP_md=$'\e[1;36m'     # begin bold (NORD7, Frost turquoise)
export LESS_TERMCAP_me=$'\e[0m'        # reset bold/blink
export LESS_TERMCAP_so=$'\e[01;44;33m' # begin standout-mode - info box (NORD13, Aurora yellow on NORD0, Polar Night)
export LESS_TERMCAP_se=$'\e[0m'        # reset standout-mode
export LESS_TERMCAP_us=$'\e[1;32m'     # begin underline (NORD14, Aurora green)
export LESS_TERMCAP_ue=$'\e[0m'        # reset underline

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
# 8. Functions
# ------------------------------------------------------------------------------

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

# function alias
alias venv='setup_venv'

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

# function alias
alias v='enable_venv'

compile_and_run_c() {
    # Find the .c file in the current directory
    local c_file=$(find . -maxdepth 1 -type f -name "*.c" | head -n 1)

    # Check if a .c file was found
    if [[ -z "$c_file" ]]; then
        echo "No .c file found in the current directory."
        return 1
    fi

    # Extract the base name (without extension) for the executable
    local base_name=$(basename "$c_file" .c)

    # Compile the .c file
    echo "Compiling $c_file..."
    if gcc "$c_file" -o "$base_name"; then
        echo "Compilation successful. Running $base_name..."
        ./"$base_name"
    else
        echo "Compilation failed."
        return 1
    fi
}

# function alias
alias crc="compile_and_run_c"

# ------------------------------------------------------------------------------
# 9. Bash completion (FreeBSD specific)
# ------------------------------------------------------------------------------
if [ -f /usr/local/share/bash-completion/bash_completion.sh ]; then
    . /usr/local/share/bash-completion/bash_completion.sh
fi

# ------------------------------------------------------------------------------
# 10. Extractor function
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