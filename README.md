# Bash Scripts Repository

Welcome to my **Bash Scripts Repository**! This collection of scripts automates system setup, configuration, and maintenance tasks for **FreeBSD** and **Linux** (primarily Ubuntu). Whether you're setting up a new system, managing backups, or configuring development environments, these scripts save time and reduce manual effort.

---

## Table of Contents

- [Bash Scripts Repository](#bash-scripts-repository)
  - [Table of Contents](#table-of-contents)
  - [Overview](#overview)
  - [Usage](#usage)
  - [Script Highlights](#script-highlights)
    - [FreeBSD](#freebsd)
    - [Linux](#linux)
  - [Contributions](#contributions)
  - [License](#license)
  - [Contact](#contact)

---

## Overview

The repository is organized into two main directories:

- **FreeBSD**: Scripts for FreeBSD system setup, backups, and development environments.
- **Linux**: Scripts for Ubuntu and other Linux distributions, including system configuration, Docker helpers, and backup utilities.

---

## Usage

1. **Clone the Repository**:

   ```bash
   git clone https://github.com/dunamismax/bash.git
   cd bash
   ```

2. **Run a Script**:
   Navigate to the desired script (e.g., `freebsd/install-v2.sh` or `linux/ubuntu/install.sh`), make it executable, and run it:

   ```bash
   chmod +x script_name.sh
   ./script_name.sh
   ```

   Most scripts require `sudo` for system-level changes.

3. **Customize**:
   Edit scripts to adjust variables like backup locations or package lists.

---

## Script Highlights

### FreeBSD

- **`install-v2.sh`**: Automated FreeBSD setup (packages, SSH, etc.).
- **`backup_system.sh`**: System backup utility.
- **`plex_backup.sh`**: Plex Media Server backup.

### Linux

- **`ubuntu/install.sh`**: Ubuntu system setup and configuration.
- **`backup_system.sh`**: General system backup.
- **`docker-compose-up.sh`**: Docker Compose helper.
- **`upload-backups-to-B2.sh`**: Backblaze B2 backup uploader.

---

## Contributions

Contributions are welcome! Fork the repository, make your changes, and submit a pull request.

---

## License

This repository is licensed under the [MIT License](./LICENSE).

---

## Contact

- **GitHub**: [dunamismax](https://github.com/dunamismax)
- **Bluesky**: [dunamismax.bsky.social](https://bsky.app/profile/dunamismax.bsky.social)

Feel free to reach out with questions or suggestions!

---

**Thank you for visiting!** 🚀

---

This version is concise, skips the repository structure chart, and focuses on the essentials. Let me know if you'd like further tweaks!
