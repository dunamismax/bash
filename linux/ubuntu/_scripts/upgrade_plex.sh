#!/usr/bin/env bash
set -Eeuo pipefail

# Variables
PLEX_URL="https://downloads.plex.tv/plex-media-server-new/1.41.4.9463-630c9f557/debian/plexmediaserver_1.41.4.9463-630c9f557_amd64.deb"
TEMP_DEB="/tmp/plexmediaserver.deb"

echo "Downloading Plex Media Server package..."
if ! curl -L -o "$TEMP_DEB" "$PLEX_URL"; then
    echo "Error: Failed to download Plex package." >&2
    exit 1
fi

echo "Installing Plex Media Server..."
if ! dpkg -i "$TEMP_DEB"; then
    echo "Dependency issues detected. Attempting to fix dependencies..."
    if ! apt-get install -f -y; then
        echo "Error: Failed to resolve dependencies for Plex." >&2
        exit 1
    fi
fi

echo "Cleaning up temporary files..."
rm -f "$TEMP_DEB"

echo "Restarting Plex Media Server service..."
if ! systemctl restart plexmediaserver; then
    echo "Error: Failed to restart Plex Media Server service." >&2
    exit 1
fi

echo "Plex Media Server has been updated and restarted successfully."
