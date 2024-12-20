#!/usr/bin/env bash
set -euo pipefail

# Update and install essential packages
sudo apt update && sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    build-essential \
    make \
    git \
    curl \
    wget \
    vim \
    tmux \
    unzip \
    zip \
    libssl-dev \
    libffi-dev \
    libsqlite3-dev \
    libbz2-dev \
    libreadline-dev \
    libncursesw5-dev \
    libgdbm-dev \
    libnss3-dev \
    liblzma-dev \
    zlib1g-dev \
    xz-utils \
    llvm \
    libxml2-dev \
    libxmlsec1-dev \
    default-jdk \
    nodejs \
    npm \
    docker.io \
    postgresql \
    postgresql-contrib \
    pipx \
    tk-dev \
    nginx

# Ensure that pipx's bin directory is on PATH for the current shell
export PATH="$PATH:$HOME/.local/bin"

# Upgrade pipx itself
pipx upgrade pipx

# A curated set of useful global Python CLI tools installed via pipx.
PIPX_TOOLS=(
    # From your original list:
    ansible-core       # Automation and configuration management
    cookiecutter       # Project templates
    coverage           # Code coverage reports
    flake8             # Linting
    isort              # Sort Python imports
    mypy               # Static type checking
    pip-tools          # Dependency management tools (pip-compile, pip-sync)
    pylint             # Another powerful linter
    pyupgrade          # Automatically upgrade syntax for newer Python versions
    tox                # Test automation across environments
    twine              # For publishing packages

    # Commonly used Python tools not in your original list but generally popular:
    black              # Code formatter (very common in Python dev)
    pytest             # Test framework

    # Additional CLI tools from the second list or commonly used:
    ipython            # Enhanced Python REPL
    rich-cli           # Rich text formatting on the command line
    tldr               # Simplified man pages
    yt-dlp             # YouTube and media downloader
)

# Install each tool with pipx
for tool in "${PIPX_TOOLS[@]}"; do
    echo "Installing $tool with pipx..."
    pipx install "$tool" || true
done

echo "All done! System and Python tooling are installed."
