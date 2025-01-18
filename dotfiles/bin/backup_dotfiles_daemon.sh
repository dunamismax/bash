#!/bin/bash

# Run the backup script every minute
while true; do
    ~/.local/bin/backup_dotfiles.sh >> ~/.config/i3/backup_log.txt 2>&1
    sleep 60
done