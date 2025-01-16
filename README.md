# Bash

Welcome to the “Bash” repository, where I store all of my Bash scripts and related material! This repository contains a variety of shell scripts meant for automating tasks on different *nix platforms, including CentOS, Debian, Ubuntu, and FreeBSD. You’ll also find additional generic scripts under the [Scripts](./Scripts/) directory that can be adapted to your own workflow.

---

## Table of Contents
- [Bash](#bash)
  - [Table of Contents](#table-of-contents)
  - [Overview](#overview)
  - [Project Structure](#project-structure)
  - [Usage](#usage)
  - [Scripts Overview](#scripts-overview)
  - [Contributions](#contributions)
  - [License](#license)
  - [Contact](#contact)

---

## Overview

This collection contains installation scripts, system configuration helpers, backup utilities, and more. Whether you’re preparing a new system or automating tasks on an existing one, these Bash scripts can save time and reduce the chance of manual errors.

Key highlights:
- Versatile scripts for **Debian**, **CentOS**, **Ubuntu**, and **FreeBSD**.
- Backup and restore scripts using tools like `restic` and `docker-compose`.
- Tools for updating DNS, setting up Python development environments, transferring backups to Backblaze B2, and more.

---

## Project Structure

Below is an outline of how the repository is organized:

```
Bash
├── CentOS
│   └── install.sh                # CentOS-specific installation script
├── Debian
│   └── install.sh                # Debian-specific installation script
├── FreeBSD
│   └── FreeBSD-System-Config.sh  # FreeBSD-specific system configuration script
├── Scripts
│   ├── docker-compose-up.sh      # Helper for bringing up Docker Compose projects
│   ├── home-backup.sh            # Home directory backup
│   ├── plex-media-backup.sh      # Backup for Plex Media data
│   ├── python-dev-setup.sh       # Sets up Python development environment
│   ├── restic-backup.sh          # General restic backup script
│   ├── restic-plex-backup.sh     # restic backup specifically targeting Plex
│   ├── update_all_dns.sh         # Updates DNS records (example usage for multiple providers)
│   └── upload-backups-to-B2.sh   # Uploads backups to Backblaze B2
├── ubuntu
│   └── config.sh                 # Ubuntu-specific configuration script
├── LICENSE
└── README.md                     # This README
```

---

## Usage

1. **Cloning the repository**
   To get started, clone the repository:
   ```bash
   git clone https://github.com/dunamismax/Bash.git
   cd Bash
   ```

2. **Navigating**
   - If you’re configuring a fresh machine, jump into one of the OS-specific folders (e.g., `Debian`, `ubuntu`, `CentOS`, or `FreeBSD`) and review the `install.sh` or `.sh` script.
   - If you just need a general script (like a backup helper), check the `Scripts` directory.

3. **Running a script**
   Make sure the script is executable:
   ```bash
   chmod +x install.sh
   ./install.sh
   ```
   or invoke the script with Bash explicitly:
   ```bash
   bash install.sh
   ```
   The scripts often require elevated privileges (`sudo`), especially if they install packages or modify system files.

4. **Customization**
   Many scripts have configurable variables (like backup destinations, DNS record details, or package lists). Open the script in your editor of choice, adjust variables, and then run it.

---

## Scripts Overview

Below is a quick summary of some notable scripts:

- **CentOS/install.sh**
  Installs core packages and performs other CentOS-specific setup tasks.

- **Debian/install.sh**
  Automates essential package installation and system configuration on Debian-based systems.

- **FreeBSD/FreeBSD-System-Config.sh**
  Helps configure a FreeBSD system, installing packages and making system-level changes.

- **Scripts/docker-compose-up.sh**
  Convenience script to bring up Docker Compose projects, possibly with custom logging or environment variable handling.

- **Scripts/home-backup.sh**
  Creates backups of your home directory, typically archiving and storing them in a local or remote location.

- **Scripts/plex-media-backup.sh**
  Backs up Plex Media Server data to a specified location.

- **Scripts/python-dev-setup.sh**
  Sets up a Python development environment (e.g., creating virtual environments, installing pyenv/pipx, etc.).

- **Scripts/restic-backup.sh** and **Scripts/restic-plex-backup.sh**
  Perform backups using [restic](https://restic.net). The `plex` version is tailored specifically for Plex.

- **Scripts/update_all_dns.sh**
  Updates DNS records (commonly includes calls to API endpoints for multiple DNS providers).

- **Scripts/upload-backups-to-B2.sh**
  Uploads backups to [Backblaze B2](https://www.backblaze.com/b2/) for remote storage.

---

## Contributions

I appreciate any suggestions or improvements. If you’d like to contribute:
1. **Fork** this repository to your GitHub account.
2. **Create** a new branch for your changes, commit your updates, and push the branch.
3. **Open** a pull request (PR) against the `main` branch of this repository.
Feel free to file issues or feature requests in the [Issues](../../issues) section.

---

## License

This repository is released under the [MIT License](./LICENSE). Feel free to use, modify, or distribute the scripts as allowed under the MIT License.

---

## Contact

• GitHub: [dunamismax](https://github.com/dunamismax)
• Bluesky: [dunamismax.bsky.social](https://bsky.app/profile/dunamismax.bsky.social)

If you have questions, suggestions, or just want to say hello, feel free to reach out via GitHub issues or on Bluesky. I’m always happy to hear about new ideas or ways you’re using these scripts!

---

**Thank you for visiting!**