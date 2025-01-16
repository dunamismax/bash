#!/bin/bash

################################################################################
# Function: Install GUI
################################################################################
install_gui() {
    log INFO "Starting installation of GUI components..."

    # Ensure non-interactive environment
    export DEBIAN_FRONTEND=noninteractive

    # Step 1: Update package lists
    log INFO "Updating package lists..."
    if apt update -y; then
        log INFO "Successfully updated package lists."
    else
        log ERROR "Failed to update package lists. Exiting."
        exit 10
    fi

    # Step 2: Install GNOME Desktop, GNOME Tweaks, and additional fonts
    log INFO "Installing GNOME Desktop, GNOME Tweaks, and additional fonts..."
    if apt install -y gnome gnome-tweaks gnome-shell-extensions gnome-software \
       gnome-terminal gnome-control-center fonts-cantarell fonts-dejavu \
       fonts-ubuntu adwaita-icon-theme-full ttf-mscorefonts-installer \
       fonts-roboto fonts-open-sans fonts-droid-fallback fonts-liberation \
       fonts-powerline; then
        log INFO "Successfully installed GUI components and additional fonts."
    else
        log ERROR "Failed to install GUI components. Exiting."
        exit 20
    fi

    # Step 3: Clean up unnecessary packages
    log INFO "Cleaning up unnecessary packages..."
    if apt autoremove -y && apt autoclean -y; then
        log INFO "System cleanup complete."
    else
        log WARN "System cleanup encountered issues. Proceeding anyway."
    fi

    # Completion message
    log INFO "Installation of GUI components and fonts complete."
    log INFO "Consider restarting the system with 'reboot' or restarting the display manager with 'systemctl restart gdm'."
}

################################################################################
# Main
################################################################################
if [ "$(id -u)" -ne 0 ]; then
    log ERROR "This script must be run as root. Exiting."
    exit 1
fi

install_gui