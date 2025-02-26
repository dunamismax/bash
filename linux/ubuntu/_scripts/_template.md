# AI Prompt for Python Script Generation

This enhanced prompt instructs you to generate Python scripts that are robust, visually appealing, and extremely user-friendly by following a standardized template. The template uses the Nord color palette for all terminal output, detailed logging with log-level filtering, strict error handling, and graceful signal handling.

---

## Enhanced Prompt Instructions

### Objective

Create Python scripts using a consistent and modern style. Use the provided template as the foundation. The script must:

- Utilize the Nord color palette for clear, colorful feedback.
- Include detailed logging with log-level filtering.
- Employ strict error handling and proper cleanup.

### Requirements

1. **Structure & Organization**

   - **Sections:** Organize the script into clear sections for configuration, logging, helper functions, main logic, and cleanup.
   - **Modularity:** Use functions for logging, error handling, and core functionality to promote modularity.
   - **Docstrings:** Include clear docstrings for functions and classes.

2. **Styling & Formatting**

   - **Indentation & Spacing:** Follow PEP 8 guidelines for indentation and spacing throughout the script.
   - **Naming Conventions:** Use `snake_case` for variables and function names, `CamelCase` for classes, and `UPPERCASE` for constants.
   - **Comments:** Include descriptive comments and clear section headers to document each part of the script.

3. **Nord Color Theme**

   - **Color Integration:** Integrate the Nord color palette (using 24-bit ANSI escape sequences) to provide visually engaging output.
   - **Log Levels & UI Elements:** Assign distinct Nord colors to different log levels (e.g., DEBUG, INFO, WARN, ERROR, CRITICAL) and to UI elements such as section headers.

4. **Error Handling & Cleanup**
   - **Signal Handlers:** Implement signal handlers to deal with interrupts and termination signals.
   - **Cleanup Tasks:** Use `atexit` to ensure that cleanup tasks are performed before the script exits.
   - **Exception Handling:** Use try/except blocks to gracefully handle errors.

### Confirmation

I confirm that the enhanced template's style, structure, and features—including the Nord-themed color feedback—will serve as the standard for all future Python scripting assistance.

---

## Python Script Template

Use the following template as the foundation for your Python scripts. **Do not change any part of this template.**

```python
#!/usr/bin/env python3
"""
Script Name: ultimate_script.py
--------------------------------------------------------
Description:
  A robust, visually engaging Python script template using the Nord
  color theme, with strict error handling, log-level filtering,
  colorized output, and graceful signal handling.

Usage:
  sudo ./ultimate_script.py

Author: YourName | License: MIT | Version: 1.0.0
"""

import atexit
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
from datetime import datetime

# ------------------------------------------------------------------------------
# Environment Configuration (Modify these settings as needed)
# ------------------------------------------------------------------------------
LOG_FILE = "/var/log/ultimate_script.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
DEFAULT_LOG_LEVEL = "INFO"

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0  = '\033[38;2;46;52;64m'     # Polar Night (dark)
NORD1  = '\033[38;2;59;66;82m'     # Polar Night (darker than NORD0)
NORD8  = '\033[38;2;136;192;208m'  # Frost (light blue)
NORD9  = '\033[38;2;129;161;193m'  # Bluish (DEBUG)
NORD10 = '\033[38;2;94;129;172m'   # Accent Blue (section headers)
NORD11 = '\033[38;2;191;97;106m'   # Reddish (ERROR/CRITICAL)
NORD13 = '\033[38;2;235;203;139m'  # Yellowish (WARN)
NORD14 = '\033[38;2;163;190;140m'  # Greenish (INFO)
NC     = '\033[0m'                 # Reset / No Color

# ------------------------------------------------------------------------------
# CUSTOM LOGGING
# ------------------------------------------------------------------------------

class NordColorFormatter(logging.Formatter):
    """
    A custom formatter that applies Nord color theme to log messages.
    """
    def __init__(self, fmt=None, datefmt=None, use_colors=True):
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors and not DISABLE_COLORS

    def format(self, record):
        levelname = record.levelname
        msg = super().format(record)

        if not self.use_colors:
            return msg

        if levelname == 'DEBUG':
            return f"{NORD9}{msg}{NC}"
        elif levelname == 'INFO':
            return f"{NORD14}{msg}{NC}"
        elif levelname == 'WARNING':
            return f"{NORD13}{msg}{NC}"
        elif levelname in ('ERROR', 'CRITICAL'):
            return f"{NORD11}{msg}{NC}"
        return msg

def setup_logging():
    """
    Set up logging with console and file handlers, using Nord color theme.
    """
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    # Create logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Clear any existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    # Console handler with colors
    console_formatter = NordColorFormatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler (no colors in file)
    file_formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    try:
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logger.warning(f"Failed to set permissions on log file {LOG_FILE}: {e}")

    return logger

def print_section(title: str):
    """
    Print a section header with Nord theme styling.
    """
    if not DISABLE_COLORS:
        border = "─" * 60
        logging.info(f"{NORD10}{border}{NC}")
        logging.info(f"{NORD10}  {title}{NC}")
        logging.info(f"{NORD10}{border}{NC}")
    else:
        border = "─" * 60
        logging.info(border)
        logging.info(f"  {title}")
        logging.info(border)

# ------------------------------------------------------------------------------
# SIGNAL HANDLING & CLEANUP
# ------------------------------------------------------------------------------

def signal_handler(signum, frame):
    """
    Handle termination signals gracefully.
    """
    if signum == signal.SIGINT:
        logging.error("Script interrupted by SIGINT (Ctrl+C).")
        sys.exit(130)
    elif signum == signal.SIGTERM:
        logging.error("Script terminated by SIGTERM.")
        sys.exit(143)
    else:
        logging.error(f"Script interrupted by signal {signum}.")
        sys.exit(128 + signum)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def cleanup():
    """
    Perform cleanup tasks before exit.
    """
    logging.info("Performing cleanup tasks before exit.")
    # Additional cleanup tasks can be added here

atexit.register(cleanup)

# ------------------------------------------------------------------------------
# DEPENDENCY CHECKING
# ------------------------------------------------------------------------------

def check_dependencies():
    """
    Check for required dependencies.
    """
    required_commands = ["command1", "command2"]
    for cmd in required_commands:
        if not shutil.which(cmd):
            logging.error(f"The '{cmd}' command is not found in your PATH. Please install it and try again.")
            sys.exit(1)

# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------

def check_root():
    """
    Ensure the script is run with root privileges.
    """
    if os.geteuid() != 0:
        logging.error("This script must be run as root.")
        sys.exit(1)

def function_one():
    """
    First main function of the script.
    """
    print_section("Starting Function One")
    logging.info("Executing tasks in function_one...")
    # Replace with actual work
    logging.info("function_one completed successfully.")

def function_two():
    """
    Second main function of the script.
    """
    print_section("Starting Function Two")
    logging.info("Executing tasks in function_two...")
    # Replace with actual work
    logging.info("function_two completed successfully.")

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------

def main():
    """
    Main entry point for the script.
    """
    setup_logging()
    check_dependencies()
    check_root()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"SCRIPT STARTED AT {now}")
    logging.info("=" * 80)

    # Execute main functions
    function_one()
    function_two()

    # Finish up
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"SCRIPT COMPLETED SUCCESSFULLY AT {now}")
    logging.info("=" * 80)

if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.error(f"Unhandled exception: {ex}")
        sys.exit(1)
```

---

## Example: Real-World Implementation

This template has been used to create a unified backup script that handles system, VM, and Plex backups with B2 cloud storage integration:

```python
#!/usr/bin/env python3
"""
Comprehensive Unified Backup Script
-----------------------------------
Description:
  A unified backup solution that performs three types of backups to Backblaze B2:
    1. System Backup - Backs up the entire system (/)
    2. VM Backup - Backs up libvirt virtual machine configurations and disk images
    3. Plex Backup - Backs up Plex Media Server configuration and application data

  Each backup is stored in a separate repository within the same B2 bucket.
  All repositories are named with the hostname prefix for organization.
  The script automatically initializes repositories as needed, forces unlocks before backup,
  and enforces retention policies.

Usage:
  sudo ./unified_backup.py

Author: Your Name | License: MIT | Version: 3.0.0
"""

import atexit
import logging
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
from datetime import datetime

# ------------------------------------------------------------------------------
# Environment Configuration (Modify these settings as needed)
# ------------------------------------------------------------------------------
# Backblaze B2 Backup Repository Credentials and Bucket
B2_ACCOUNT_ID = "12345678"
B2_ACCOUNT_KEY = "12345678"
B2_BUCKET = "sawyer-backups"

# Determine the hostname to uniquely name the repositories
HOSTNAME = socket.gethostname()

# Repository configuration
B2_REPO_SYSTEM = f"b2:{B2_BUCKET}:{HOSTNAME}/ubuntu-system-backup"
B2_REPO_VM = f"b2:{B2_BUCKET}:{HOSTNAME}/vm-backups"
B2_REPO_PLEX = f"b2:{B2_BUCKET}:{HOSTNAME}/plex-media-server-backup"

# [Additional configuration code removed for brevity]

# Logging Configuration
LOG_FILE = "/var/log/unified_backup.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
DEFAULT_LOG_LEVEL = "INFO"

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
# [Same as template]

# ------------------------------------------------------------------------------
# CUSTOM LOGGING
# ------------------------------------------------------------------------------
# [Same as template]

# ------------------------------------------------------------------------------
# SIGNAL HANDLING & CLEANUP
# ------------------------------------------------------------------------------
# [Same as template]

# ------------------------------------------------------------------------------
# REPOSITORY OPERATIONS
# ------------------------------------------------------------------------------
def run_restic(repo: str, password: str, *args, check=True, capture_output=False):
    """
    Run a restic command with appropriate environment variables.
    """
    env = os.environ.copy()
    env["RESTIC_PASSWORD"] = password
    if repo.startswith("b2:"):
        env["B2_ACCOUNT_ID"] = B2_ACCOUNT_ID
        env["B2_ACCOUNT_KEY"] = B2_ACCOUNT_KEY
    cmd = ["restic", "--repo", repo] + list(args)
    logging.info(f"Running restic command: {' '.join(cmd)}")

    # [Rest of function omitted for brevity]

# [Additional backup functions removed for brevity]

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
def main():
    """
    Main entry point for the script.
    """
    setup_logging()
    check_dependencies()

    if os.geteuid() != 0:
        logging.error("This script must be run as root.")
        sys.exit(1)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"UNIFIED BACKUP STARTED AT {now}")
    logging.info("=" * 80)

    # [Main backup logic omitted for brevity]

    # Finish up
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"UNIFIED BACKUP COMPLETED SUCCESSFULLY AT {now}")
    logging.info("=" * 80)

if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.error(f"Unhandled exception: {ex}")
        sys.exit(1)
```

---

## Final Instruction

Use this refined template as the foundation for all future Python scripts. It establishes a robust standard for error handling, logging, and user feedback while showcasing the elegant Nord color theme.

Before generating any code, please ask the user what further assistance they require. **Do not provide any additional feedback or produce any code yet.**
