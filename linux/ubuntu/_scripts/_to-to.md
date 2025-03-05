```
└── 📁_scripts
    *└── _bashrc_cheat_sheet.md
    *└── _template.md
    *└── _to-to.md
    └── deploy_scripts.py
    └── file_toolkit.py
    └── hacker_toolkit.py
    └── hacking_tools.py
    └── hello_world.py
    └── log_monitor.py
    └── metasploit.py
    └── network_toolkit.py
    └── owncloud_setup.py
    └── python_dev_setup.py
    └── raspberry_pi_5_overclocking_utility.py
    *└── reset_tailscale.py
    └── secure_disk_eraser.py
    └── sftp_toolkit.py
    └── ssh_machine_selector.py
    └── system_monitor.py
    └── ubuntu_voip_setup.py
    └── unified_backup_restore_deployment.py
    └── unified_backup.py
    └── unified_restore_to_home.py
    └── universal_downloader.py
    └── update_dns_records.py
    └── update_plex.py
    └── upgrade_debian_to_trixie_stable.py
    └── virtualization_setup.py
    └── vm_manager.py
    └── vscode_wayland_setup.py
    └── zfs_setup.py
```


Prompt 1 (Interactive CLI):

Rewrite and enhance the following Python script following the Advanced Terminal Application guidelines. The updated version should feature:

- Professional UI Implementation with a Nord color theme throughout all interface elements
- A fully interactive, menu-driven interface with numbered options and validation
- Dynamic ASCII banner using Pyfiglet with gradient styling that adapts to terminal width
- Rich library integration for panels, tables, spinners, and progress tracking with real-time statistics
- prompt_toolkit integration for tab completion, command history, and enhanced user input
- Comprehensive error handling with color-coded messaging and recovery mechanisms
- Signal handling for graceful termination (SIGINT, SIGTERM)
- Type annotations and dataclasses for improved code readability
- Cross-platform compatibility with appropriate environment detection
- Modular organization with clearly commented sections and separation of concerns

Ensure the script maintains its core functionality while implementing these enhancements for a production-grade, professional user experience. The application should be purely interactive with no command-line argument parsing. Use prompt_toolkit for any cli input or user prompting if needed and use Rich and Pyfiglet throughout. The script should also install all python / pip dependencies before executing the normal part of the script and it should try to install them system wide using Nala with "nala install python3-rich, and nala install python3-pyfiglet" etc and also try installing them as the standard non root user using pip (all the scripts are run as sudo so keep that in mind for this part) also install Nala at the start of the script and then use Nala instead of Apt for all subsequent apt commands ("apt install nala" is how you install it)

---------------------------------------------------------------------------------------------

Prompt 2 (Unattended/Automated Script):

Rewrite and enhance the following Python script following the Advanced Terminal Application guidelines for an unattended operation mode. The updated version should:

- Run fully autonomously while maintaining professional terminal output with Nord color theme
- Display a dynamic ASCII banner using Pyfiglet with gradient styling at startup
- Implement Rich library components for enhanced visual feedback:
  - Progress bars with detailed statistics for tracking long-running operations
  - Spinners with descriptive status messages for indeterminate processes
  - Panels and styled text for clear section delineation and results reporting
- Include comprehensive error handling with detailed logging and recovery mechanisms
- Implement robust signal handling for graceful termination in unattended environments
- Organize code with a modular structure and clearly commented sections
- Use type annotations and appropriate data structures for improved maintainability
- Ensure cross-platform compatibility with environment-aware operation
- Implement proper resource management and cleanup procedures

The script should maintain its core functionality while operating completely unattended without requiring user input, providing clear visual feedback about its operation status at all times. The application should just run fully unattended with no command-line argument parsing. The script should also install all python / pip dependencies before executing the normal part of the script and it should try to install them system wide using Nala with "nala install python3-rich, and nala install python3-pyfiglet" etc and also try installing them as the standard non root user using pip (all the scripts are run as sudo so keep that in mind for this part) also install Nala at the start of the script and then use Nala instead of Apt for all subsequent apt commands ("apt install nala" is how you install it)



**Nala Command Cheat Sheet**

### Basic Usage
- **Install Packages:**  
  `nala install [--options] PKGS ...`  
  _Example:_ `nala install tmux`

- **Install Specific Version:**  
  `nala install pkg=version`  
  _Example:_ `nala install tmux=3.3a-3~bpo11+1`

- **Install from URL:**  
  `nala install <URL>`  
  _Example:_ `nala install https://example.org/path/to/pkg.deb`

---

### Common Options

- **General:**
  - `-h, --help`  
    Show help/man page.
  - `--debug`  
    Print debug information for troubleshooting.
  - `-v, --verbose`  
    Disable scrolling text & show extra details.
  - `-o, --option <option>`  
    Pass options to apt/nala/dpkg.  
    _Examples:_  
    `nala install --option Dpkg::Options::="--force-confnew"`  
    `nala install --option Nala::scrolling_text="false"`

- **Transaction Control:**
  - `--purge`  
    Purge packages that would be removed during the transaction.
  - `-d, --download-only`  
    Only download packages (do not unpack/install).
  - `--remove-essential`  
    Allow removal of essential packages (use with caution).

- **Release & Updates:**
  - `-t, --target-release <release>`  
    Install from a specific release.  
    _Example:_ `nala install --target-release testing neofetch`
  - `--update` / `--no-update`  
    Update package list before operation.  
    _Example:_ `nala install --update neofetch`

- **Prompt Options:**
  - `-y, --assume-yes`  
    Automatically answer "yes" to prompts.
  - `-n, --assume-no`  
    Automatically answer "no" to prompts.

- **Display & Output:**
  - `--simple` / `--no-simple`  
    Toggle between a simple (condensed) or detailed transaction summary.
  - `--raw-dpkg`  
    Disable dpkg output formatting (no progress bar; output as in apt).

- **Dependency Management:**
  - `--autoremove` / `--no-autoremove`  
    Automatically remove unneeded packages (default is autoremove).
  - `--install-recommends` / `--no-install-recommends`  
    Toggle installation of recommended packages (default installs them).
  - `--install-suggests` / `--no-install-suggests`  
    Toggle installation of suggested packages (default installs them).
  - `--fix-broken` / `--no-fix-broken`  
    Attempt to fix broken packages (default is to fix).  
    _Tip:_ Run `nala install --fix-broken` if you encounter issues.



---------------------------------------------------------------------------------------------

rewrite (o3-mini-high)
using new prompt
