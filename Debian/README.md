# Debian/Ubuntu Automated System Configuration Script

---

## Introduction

This script is designed to automate the setup and configuration of a fresh Debian or Ubuntu system. It installs essential packages, performs security hardening measures, and optionally sets up additional software such as GNOME, Caddy, and more. The end goal is to have a ready-to-use system with sensible defaults and security best practices.

## Features at a Glance

1. Updates and upgrades your system using apt.
2. Installs a list of baseline tools and utilities (e.g., bash, Vim, Python, developer toolchains, etc.).
3. Secures SSH by backing up and overwriting /etc/ssh/sshd_config.
4. Creates a new user (“sawyer”) with Bash as the default shell.
5. Configures a firewall (ufw) with pre-defined service and port rules.
6. Installs and configures the Caddy web server.
7. Sets up system time synchronization via chrony.
8. Configures and enables unattended upgrades.
9. Optionally installs the GNOME desktop environment, AwesomeWM, and configures a graphical target on Debian or Ubuntu.
10. Performs final system cleanup.

## Requirements

- A fresh Debian or Ubuntu installation.
- Root privileges (either run as root or via sudo).
- A stable internet connection (the script pulls in packages from online repositories).

## How to Use

1. Ensure you have a clean Debian or Ubuntu system ready.
2. Copy or download this script to your server or VM.
3. Make the script executable:
   ```bash
   chmod +x path/to/this_script.sh
   ```
4. Run the script as root or via sudo:
   ```bash
   sudo ./this_script.sh
   ```
   You may also pass additional arguments to the script if it supports them; by default, there are no user-level arguments.

## Logging

- All major actions are logged in `/var/log/debian_setup.log`.
- Errors are caught and displayed, and the script will exit on unexpected errors (due to `set -Eeuo pipefail` plus a trap on `ERR`).

## Important Notes

- This script creates a user named “sawyer” and sets that user’s default shell to Bash. If you need a different username, modify the `USERNAME` variable at the top of the script.
- The script backs up certain files (like `/etc/ssh/sshd_config`) before overwriting them. These backups typically use the `.bak` extension, sometimes with a timestamp for safety.
- The script attempts to enable and configure GNOME, gdm3, and AwesomeWM. If you do not need a GUI environment on your server, remove or comment out the relevant sections (e.g., `enable_gui`).
- By default, it sets the hostname to “debian” and the timezone to “America/New_York” in the `main()` function. Adjust these parameters as needed.
- The script installs and configures the Caddy web server, placing a default Caddyfile in `/etc/caddy/Caddyfile`. Modify the domain names and site configuration for your needs.

## Troubleshooting & Support

- Check the log file at `/var/log/debian_setup.log` if you run into issues. Additionally, check the logs for services like `systemctl status caddy` or `systemctl status fail2ban` if they fail to start.
- Confirm that the user “sawyer” was created and has the correct shell by running `grep sawyer /etc/passwd`.
- If ufw rules are not applying, manually run `ufw status` to see if the rules were added.
- For further security, consider customizing the firewall ports, SSH configurations, and adding advanced intrusion detection solutions beyond `fail2ban` and `AIDE`.