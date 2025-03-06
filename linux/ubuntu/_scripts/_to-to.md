```
└── 📁_scripts
    *└── _bashrc_cheat_sheet.md
    *└── _template.md
    *└── _to-to.md
    └── deploy_scripts.py
    └── fail2ban_toolkit.py
    └── file_toolkit.py
    └── fix_ssh_tool.py
    └── git_commander.py
    └── hacker_toolkit.py
    └── hacking_tools.py
    └── hello_world.py
    └── log_monitor.py
    └── metasploit.py
    └── network_toolkit.py
    *└── nextcloud_setup.py
    └── python_dev_setup.py
    └── raspberry_pi_5_overclocking_utility.py
    └── reset_tailscale.py
    └── secure_disk_eraser.py
    └── sftp_toolkit.py
    *└── ssh_machine_selector.py
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

---------------------------------------------------------------------------------------------

Prompt 1 (Interactive CLI):
Create an interactive terminal application following the Advanced Terminal Application Generator standards. The application must include:

Professional UI with the Nord color theme palette consistently applied to all interface elements.
Interactive, menu-driven interface with numbered options, validation, and intuitive navigation.
Dynamic ASCII banner headers using Pyfiglet with frost gradient coloring that adapts to terminal width.
Rich library integration for panels, tables, spinners, and real-time progress tracking of operations.
Comprehensive error handling with color-coded messaging (green for success, yellow for warnings, red for errors).
Signal handlers for SIGINT and SIGTERM to ensure graceful application termination.
Type annotations for all function signatures and dataclasses for structured data.
Standardized section structure following the exact order: dependencies, configuration, Nord colors, data structures, UI helpers, core functionality, signal handling, interactive menu, and entry point.

Build the application with a production-grade user experience focusing on responsiveness, error recovery, and visual consistency. The application must work on Ubuntu without modification and should not use argparse or implement command-line arguments.

---------------------------------------------------------------------------------------------

Prompt 2 (Unattended/Automated Script):
Create an automated terminal application that adheres to the Advanced Terminal Application Generator standards. This application must:

Execute autonomously with professional terminal output using the Nord color theme.
Display a dynamic ASCII banner with Pyfiglet and frost gradient styling at startup and for each major operational phase.
Integrate the Rich library for visual feedback, including:

Progress bars with spinners for long-running operations
Panels with appropriate titles for information sections
Color-coded status messaging (green for success, yellow for warnings, red for errors)


Implement robust error handling with try/except blocks around all external operations and file I/O.
Include signal handlers for SIGINT and SIGTERM to perform appropriate cleanup on termination.
Follow the standardized structure with clearly demarcated sections using delimiter comments.
Ensure proper resource management with cleanup operations that run even during abnormal termination.

The application should operate without user interaction while providing clear, real-time visual feedback on its progress and status. It must work on Ubuntu without modification and should not use argparse or implement command-line arguments.

---------------------------------------------------------------------------------------------

rewrite (claude 3.7 sonnet)
using new prompt
