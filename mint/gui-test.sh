################################################################################
# Function: Install GUI
################################################################################
install_gui() {
    log INFO "Starting installation of GUI components..."

    # Ensure non-interactive environment
    export DEBIAN_FRONTEND=noninteractive

    # Step 1: Update package lists
    log INFO "Updating package lists..."
    if apt update; then
        log INFO "Successfully updated package lists."
    else
        log ERROR "Failed to update package lists. Exiting."
        exit 10
    fi

    # Step 2: Install GNOME Desktop and GNOME Tweaks
    log INFO "Installing GNOME Desktop and GNOME Tweaks..."
    local gnome_packages="gnome gnome-tweaks gnome-shell-extensions gnome-software gnome-terminal gnome-control-center fonts-cantarell fonts-dejavu fonts-ubuntu adwaita-icon-theme-full"

    for pkg in $gnome_packages; do
        if ! dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "install ok installed"; then
            install_required=1
            break
        fi
    done

    if [ "$install_required" == "1" ]; then
        if apt install -y "$gnome_packages"; then
            log INFO "Successfully installed GNOME Desktop and related packages."
        else
            log ERROR "Failed to install GNOME Desktop. Exiting."
            exit 20
        fi
    else
        log INFO "GNOME Desktop is already installed. Skipping."
    fi

    # Step 3: Install Fonts
    log INFO "Installing additional fonts..."
    local fonts="ttf-mscorefonts-installer fonts-roboto fonts-open-sans fonts-droid-fallback fonts-liberation fonts-powerline"
    if apt install -y "$fonts"; then
        log INFO "Successfully installed fonts."
    else
        log ERROR "Failed to install fonts. Exiting."
        exit 40
    fi

    # Step 4: Clean up
    log INFO "Cleaning up unnecessary packages..."
    if apt autoremove -y && apt autoclean -y; then
        log INFO "System cleanup complete."
    else
        log WARN "System cleanup encountered issues. Proceeding anyway."
    fi

    # Completion message
    log INFO "Installation of GUI components and Window Managers complete."
    log INFO "Consider restarting the system with 'reboot' or restarting the display manager with 'systemctl restart gdm'."
}