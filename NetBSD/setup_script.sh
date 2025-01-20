#!/bin/sh
# -----------------------------------------------------------------------------
# NetBSD System Configuration Script with Neovim and ZSH Setup
# -----------------------------------------------------------------------------
# Purpose: Configure a fresh NetBSD installation for software development
# and web serving, following UNIX philosophy principles.
#
# Author: Inspired by Dennis M. Ritchie's approach to system administration
# License: BSD
# -----------------------------------------------------------------------------

set -e

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
LOG_FILE="/var/log/setup.log"
USERNAME="sawyer"    # System username

# Core development tools and libraries - now including neovim and zsh dependencies
PACKAGES="
    base-devel
    gcc
    clang
    make
    vim
    neovim
    tmux
    git
    curl
    wget
    openssl
    openssh
    nginx
    sqlite3
    rsync
    htop
    lynx
    ripgrep
    fd-find
    nodejs
    npm
    python3
    python3-pip
    zsh
    zsh-autosuggestions
    zsh-syntax-highlighting
    fzf
"

# -----------------------------------------------------------------------------
# Logging function - simple and effective, as DMR would prefer
# -----------------------------------------------------------------------------
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG_FILE"
}

# -----------------------------------------------------------------------------
# Error handler - clean and straightforward
# -----------------------------------------------------------------------------
handle_error() {
    log "Error occurred at line $1"
    exit 1
}

trap 'handle_error $LINENO' ERR

# -----------------------------------------------------------------------------
# System package management
# -----------------------------------------------------------------------------
install_packages() {
    log "Updating package repository..."
    pkg_add -u

    log "Installing development packages..."
    for pkg in $PACKAGES; do
        if ! pkg_info | grep -q "^$pkg"; then
            pkg_add "$pkg"
            log "Installed: $pkg"
        fi
    done

    # Install Python packages for Neovim
    pip3 install --user pynvim neovim-remote

    # Install Node packages for Neovim
    npm install -g neovim tree-sitter-cli
}

# -----------------------------------------------------------------------------
# Configure Neovim with modern features while maintaining simplicity
# -----------------------------------------------------------------------------
setup_neovim() {
    log "Setting up Neovim configuration..."

    # Create Neovim configuration directory structure
    NVIM_CONFIG_DIR="/home/$USERNAME/.config/nvim"
    mkdir -p "$NVIM_CONFIG_DIR"/{lua,plugin}

    # Install packer.nvim (plugin manager)
    PACKER_DIR="/home/$USERNAME/.local/share/nvim/site/pack/packer/start/packer.nvim"
    if [ ! -d "$PACKER_DIR" ]; then
        git clone --depth 1 https://github.com/wbthomason/packer.nvim "$PACKER_DIR"
    fi

    # Create main init.lua configuration
    cat > "$NVIM_CONFIG_DIR/init.lua" << 'EOF'
-- Basic Settings
vim.opt.number = true
vim.opt.relativenumber = true
vim.opt.wrap = false
vim.opt.encoding = 'utf-8'
vim.opt.swapfile = false
vim.opt.backup = false
vim.opt.undodir = vim.fn.expand('~/.vim/undodir')
vim.opt.undofile = true
vim.opt.hlsearch = false
vim.opt.incsearch = true
vim.opt.termguicolors = true
vim.opt.scrolloff = 8
vim.opt.updatetime = 50
vim.opt.colorcolumn = '80'

-- Indentation
vim.opt.tabstop = 4
vim.opt.softtabstop = 4
vim.opt.shiftwidth = 4
vim.opt.expandtab = true
vim.opt.smartindent = true

-- Leader Key
vim.g.mapleader = ' '

-- Plugin Management with Packer
require('packer').startup(function(use)
    use 'wbthomason/packer.nvim'
    use 'nvim-treesitter/nvim-treesitter'
    use 'nvim-lua/plenary.nvim'
    use 'nvim-telescope/telescope.nvim'
    use 'neovim/nvim-lspconfig'
    use 'hrsh7th/nvim-cmp'
    use 'hrsh7th/cmp-nvim-lsp'
    use 'L3MON4D3/LuaSnip'
    use 'sainnhe/gruvbox-material'
    use {
        'nvim-lualine/lualine.nvim',
        requires = { 'nvim-tree/nvim-web-devicons' }
    }
end)

-- Color Scheme
vim.cmd([[
    set background=dark
    let g:gruvbox_material_background = 'hard'
    colorscheme gruvbox-material
]])

-- Treesitter Configuration
require('nvim-treesitter.configs').setup({
    ensure_installed = {
        'c', 'lua', 'vim', 'python', 'javascript',
        'typescript', 'bash', 'markdown'
    },
    highlight = { enable = true },
    indent = { enable = true }
})

-- LSP Configuration
local lspconfig = require('lspconfig')
local capabilities = require('cmp_nvim_lsp').default_capabilities()

-- Setup language servers
lspconfig.pyright.setup({ capabilities = capabilities })
lspconfig.clangd.setup({ capabilities = capabilities })
lspconfig.tsserver.setup({ capabilities = capabilities })

-- Completion Setup
local cmp = require('cmp')
cmp.setup({
    snippet = {
        expand = function(args)
            require('luasnip').lsp_expand(args.body)
        end,
    },
    mapping = cmp.mapping.preset.insert({
        ['<C-b>'] = cmp.mapping.scroll_docs(-4),
        ['<C-f>'] = cmp.mapping.scroll_docs(4),
        ['<C-Space>'] = cmp.mapping.complete(),
        ['<C-e>'] = cmp.mapping.abort(),
        ['<CR>'] = cmp.mapping.confirm({ select = true })
    }),
    sources = cmp.config.sources({
        { name = 'nvim_lsp' },
        { name = 'luasnip' },
    }, {
        { name = 'buffer' },
    })
})

-- Telescope Configuration
local telescope = require('telescope.builtin')
vim.keymap.set('n', '<leader>ff', telescope.find_files, {})
vim.keymap.set('n', '<leader>fg', telescope.live_grep, {})
vim.keymap.set('n', '<leader>fb', telescope.buffers, {})
vim.keymap.set('n', '<leader>fh', telescope.help_tags, {})

-- Status Line
require('lualine').setup({
    options = {
        theme = 'gruvbox-material',
        component_separators = '|',
        section_separators = '',
    }
})

-- Key Mappings
vim.keymap.set('n', '<leader>e', vim.diagnostic.open_float)
vim.keymap.set('n', '[d', vim.diagnostic.goto_prev)
vim.keymap.set('n', ']d', vim.diagnostic.goto_next)
vim.keymap.set('n', '<leader>q', vim.diagnostic.setloclist)

-- LSP key bindings
vim.api.nvim_create_autocmd('LspAttach', {
    group = vim.api.nvim_create_augroup('UserLspConfig', {}),
    callback = function(ev)
        local opts = { buffer = ev.buf }
        vim.keymap.set('n', 'gD', vim.lsp.buf.declaration, opts)
        vim.keymap.set('n', 'gd', vim.lsp.buf.definition, opts)
        vim.keymap.set('n', 'K', vim.lsp.buf.hover, opts)
        vim.keymap.set('n', 'gi', vim.lsp.buf.implementation, opts)
        vim.keymap.set('n', '<C-k>', vim.lsp.buf.signature_help, opts)
        vim.keymap.set('n', '<leader>wa', vim.lsp.buf.add_workspace_folder, opts)
        vim.keymap.set('n', '<leader>wr', vim.lsp.buf.remove_workspace_folder, opts)
        vim.keymap.set('n', '<leader>D', vim.lsp.buf.type_definition, opts)
        vim.keymap.set('n', '<leader>rn', vim.lsp.buf.rename, opts)
        vim.keymap.set({ 'n', 'v' }, '<leader>ca', vim.lsp.buf.code_action, opts)
        vim.keymap.set('n', 'gr', vim.lsp.buf.references, opts)
    end,
})
EOF

    # Set permissions
    chown -R "$USERNAME:wheel" "/home/$USERNAME/.config"
    chown -R "$USERNAME:wheel" "/home/$USERNAME/.local"

    # Create initial plugin installation script
    cat > "/home/$USERNAME/install_nvim_plugins.sh" << 'EOF'
#!/bin/sh
nvim --headless -c 'autocmd User PackerComplete quitall' -c 'PackerSync'
EOF

    chmod +x "/home/$USERNAME/install_nvim_plugins.sh"
    chown "$USERNAME:wheel" "/home/$USERNAME/install_nvim_plugins.sh"
}

# -----------------------------------------------------------------------------
# Configure ZSH with modern features while maintaining simplicity
# -----------------------------------------------------------------------------
setup_zsh() {
    log "Setting up ZSH configuration..."

    # Create ZSH configuration directory structure
    ZSH_CONFIG_DIR="/home/$USERNAME"
    mkdir -p "$ZSH_CONFIG_DIR"/.zsh

    # Install zimfw (ZSH framework)
    curl -fsSL https://raw.githubusercontent.com/zimfw/install/master/install.zsh | zsh

    # Create main .zshrc configuration
    cat > "$ZSH_CONFIG_DIR/.zshrc" << 'EOF'
# -----------------------------------------------------------------------------
# ZSH Configuration
# Inspired by modern shell practices while maintaining simplicity
# -----------------------------------------------------------------------------

# Core ZSH Settings
# -----------------------------------------------------------------------------
setopt AUTO_CD              # Change directory without cd
setopt EXTENDED_GLOB        # Extended globbing
setopt NOTIFY              # Report status of background jobs immediately
setopt APPEND_HISTORY      # Append to history instead of overwriting
setopt EXTENDED_HISTORY    # Save timestamp and duration
setopt SHARE_HISTORY       # Share history between sessions
setopt HIST_EXPIRE_DUPS_FIRST
setopt HIST_IGNORE_DUPS
setopt HIST_FIND_NO_DUPS
setopt HIST_REDUCE_BLANKS

# History Configuration
# -----------------------------------------------------------------------------
HISTFILE=~/.zsh_history
HISTSIZE=50000
SAVEHIST=10000

# Environment Variables
# -----------------------------------------------------------------------------
export EDITOR='nvim'
export VISUAL='nvim'
export PAGER='less'
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export TERM=xterm-256color

# Path Configuration
# -----------------------------------------------------------------------------
typeset -U path
path=(
    ~/.local/bin
    ~/.cargo/bin
    ~/.npm-global/bin
    $path
)

# Aliases
# -----------------------------------------------------------------------------
alias ls='ls -F --color=auto'
alias ll='ls -lh'
alias la='ls -lah'
alias grep='grep --color=auto'
alias vi='nvim'
alias vim='nvim'
alias tree='tree -C'
alias dc='cd'
alias ..='cd ..'
alias ...='cd ../..'
alias mkdir='mkdir -p'
alias df='df -h'
alias du='du -h'
alias free='free -m'
alias g='git'
alias ga='git add'
alias gc='git commit'
alias gp='git push'
alias gst='git status'

# Key Bindings
# -----------------------------------------------------------------------------
bindkey -e  # Use emacs key bindings
bindkey '^[[A' history-substring-search-up
bindkey '^[[B' history-substring-search-down
bindkey '^[[H' beginning-of-line
bindkey '^[[F' end-of-line
bindkey '^[[3~' delete-char
bindkey '^[[1;5C' forward-word
bindkey '^[[1;5D' backward-word

# Auto Completion
# -----------------------------------------------------------------------------
autoload -Uz compinit
compinit -d ~/.cache/zcompdump
zstyle ':completion:*' menu select
zstyle ':completion:*' matcher-list 'm:{a-zA-Z}={A-Za-z}'
zstyle ':completion:*' list-colors "${(s.:.)LS_COLORS}"
zstyle ':completion:*' verbose yes
zstyle ':completion:*' group-name ''
zstyle ':completion:*:descriptions' format '%F{green}-- %d --%f'

# Plugin Configuration
# -----------------------------------------------------------------------------
# Source external plugins
source ~/.zsh/zsh-autosuggestions/zsh-autosuggestions.zsh
source ~/.zsh/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh

# FZF Integration
# -----------------------------------------------------------------------------
[ -f ~/.fzf.zsh ] && source ~/.fzf.zsh

# Custom Functions
# -----------------------------------------------------------------------------
# Quick directory navigation
function mkcd() { mkdir -p "$@" && cd "$@"; }

# Enhanced git log
function glog() {
    git log --graph --pretty=format:'%Cred%h%Creset -%C(yellow)%d%Creset %s %Cgreen(%cr) %C(bold blue)<%an>%Creset' --abbrev-commit
}

# Quick find
function ff() { find . -name "*$1*" }

# System update shortcut
function update() {
    echo "Updating system packages..."
    sudo pkg_add -u
    echo "Updating npm packages..."
    npm update -g
    echo "Updating pip packages..."
    pip3 list --outdated --format=freeze | grep -v '^\-e' | cut -d = -f 1 | xargs -n1 pip3 install -U
}

# Prompt Configuration
# -----------------------------------------------------------------------------
autoload -Uz vcs_info
precmd() { vcs_info }
zstyle ':vcs_info:git:*' formats '%F{240}(%b)%f'
setopt prompt_subst
PROMPT='%F{blue}%~%f ${vcs_info_msg_0_} %F{green}➜%f '

# Load Local Configuration
# -----------------------------------------------------------------------------
[[ -f ~/.zshrc.local ]] && source ~/.zshrc.local
EOF

    # Set permissions
    chown -R "$USERNAME:wheel" "$ZSH_CONFIG_DIR/.zsh"
    chown "$USERNAME:wheel" "$ZSH_CONFIG_DIR/.zshrc"

    # Set ZSH as default shell
    log "Setting ZSH as default shell for $USERNAME..."
    chsh -s /usr/pkg/bin/zsh "$USERNAME"

    # Create plugins directory and symlinks
    mkdir -p "$ZSH_CONFIG_DIR/.zsh/zsh-autosuggestions"
    mkdir -p "$ZSH_CONFIG_DIR/.zsh/zsh-syntax-highlighting"
    ln -sf /usr/pkg/share/zsh-autosuggestions/zsh-autosuggestions.zsh "$ZSH_CONFIG_DIR/.zsh/zsh-autosuggestions/"
    ln -sf /usr/pkg/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh "$ZSH_CONFIG_DIR/.zsh/zsh-syntax-highlighting/"
}

# -----------------------------------------------------------------------------
# Main execution block - updated to include ZSH setup
# -----------------------------------------------------------------------------
main() {
    log "Starting NetBSD system configuration..."

    if [ "$(id -u)" -ne 0 ]; then
        echo "This script must be run as root"
        exit 1
    fi

    # Create log file
    touch "$LOG_FILE"
    chmod 600 "$LOG_FILE"

    install_packages
    configure_ssh
    setup_development
    configure_webserver
    configure_security
    setup_neovim
    setup_zsh

    log "System configuration complete."
    log "To finish Neovim setup, please run:"
    log "su - $USERNAME -c './install_nvim_plugins.sh'"
    log "ZSH has been configured and set as the default shell."
    log "Remember to run 'sync' before rebooting"
}

# Execute main function
main "$@"