#!/bin/bash

# Define source directories
SOURCE_DIRS=(
    "$HOME/.config/rofi"
    "$HOME/.config/i3"
    "$HOME/.config/gtk-3.0"
    "$HOME/.config/gtk-4.0"
    "$HOME/.local/bin/"
)

# Define destination directory
DESTINATION="$HOME/github/bash/dotfiles"

# Ensure the destination directory exists
mkdir -p "$DESTINATION"

# Backup the folders
for DIR in "${SOURCE_DIRS[@]}"; do
    if [ -d "$DIR" ]; then
        rsync -av --delete "$DIR/" "$DESTINATION/$(basename "$DIR")"
    else
        echo "Directory $DIR does not exist, skipping."
    fi
done

# Additional files (dotfiles) to backup
DOTFILES=(
    "$HOME/.bashrc"
    "$HOME/.profile"
    "$HOME/.bash_profile"
    "$HOME/.local"
    "$HOME/.bash_history"
    "$HOME/.fehbg"
)

# Backup additional dotfiles
for FILE in "${DOTFILES[@]}"; do
    if [ -f "$FILE" ]; then
        rsync -av "$FILE" "$DESTINATION/"
    else
        echo "Dotfile $FILE does not exist, skipping."
    fi
done

echo "Backup completed at $(date)."
