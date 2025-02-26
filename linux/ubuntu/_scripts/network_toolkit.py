#!/usr/bin/env python3
"""
Script Name: network_toolkit.py
--------------------------------------------------------
Description:
  An advanced, production-grade network toolkit that performs common and advanced
  network tests, diagnostics, performance measurements, and penetration testing
  tasks on Debian-based systems. This interactive tool provides a Nord-themed user
  interface with strict error handling, detailed logging, and graceful signal handling.

  Features include:
  - Basic network information gathering
  - Connectivity and DNS testing
  - Network scanning and discovery
  - Performance testing and monitoring
  - Advanced security testing
  - Firewall and WiFi diagnostics
  - SSL/TLS certificate analysis
  - Network service enumeration
  - Packet crafting and analysis
  - Report generation and result saving

Usage:
  sudo ./network_toolkit.py

Author: YourName | License: MIT | Version: 3.0.0
"""

import atexit
import csv
import datetime
import ipaddress
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.request

# ------------------------------------------------------------------------------
# Environment Configuration (Modify these settings as needed)
# ------------------------------------------------------------------------------
LOG_FILE = "/var/log/enhanced_network_toolkit.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
DEFAULT_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
CONFIG_DIR = os.path.expanduser("~/.config/enhanced_network_toolkit")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
HISTORY_FILE = os.path.join(CONFIG_DIR, "history.json")
REPORTS_DIR = os.path.join(CONFIG_DIR, "reports")
MAX_HISTORY_ITEMS = 50
MAX_THREADS = 10

# Default configuration
DEFAULT_CONFIG = {
    "ping_count": 5,
    "traceroute_max_hops": 30,
    "port_scan_default_range": "1-1024",
    "dns_servers": ["1.1.1.1", "8.8.8.8", "9.9.9.9"],
    "speedtest_server": None,  # Auto-select
    "http_timeout": 10,
    "favorite_hosts": [],
    "packet_size": 56,
    "theme": "dark",
    "recent_commands": [],
    "max_history": MAX_HISTORY_ITEMS,
    "ssl_default_timeout": 10,
    "continuous_monitoring": False,
    "autosave_results": True,
    "default_interface": "",
    "bandwidth_interval": 1.0,  # seconds
}

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0 = "\033[38;2;46;52;64m"  # Polar Night (dark)
NORD1 = "\033[38;2;59;66;82m"  # Polar Night (darker than NORD0)
NORD2 = "\033[38;2;67;76;94m"  # Polar Night (lighter)
NORD3 = "\033[38;2;76;86;106m"  # Polar Night (lightest)
NORD4 = "\033[38;2;216;222;233m"  # Snow Storm (darkest)
NORD5 = "\033[38;2;229;233;240m"  # Snow Storm (medium)
NORD6 = "\033[38;2;236;239;244m"  # Snow Storm (lightest)
NORD7 = "\033[38;2;143;188;187m"  # Frost (green-cyan)
NORD8 = "\033[38;2;136;192;208m"  # Frost (light blue)
NORD9 = "\033[38;2;129;161;193m"  # Bluish (DEBUG)
NORD10 = "\033[38;2;94;129;172m"  # Accent Blue (section headers)
NORD11 = "\033[38;2;191;97;106m"  # Reddish (ERROR/CRITICAL)
NORD12 = "\033[38;2;208;135;112m"  # Aurora (orange)
NORD13 = "\033[38;2;235;203;139m"  # Yellowish (WARN)
NORD14 = "\033[38;2;163;190;140m"  # Greenish (INFO)
NORD15 = "\033[38;2;180;142;173m"  # Purple
NC = "\033[0m"  # Reset / No Color

# Text styles
BOLD = "\033[1m"
ITALIC = "\033[3m"
UNDERLINE = "\033[4m"
BLINK = "\033[5m"
REVERSE = "\033[7m"
STRIKETHROUGH = "\033[9m"

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES
# ------------------------------------------------------------------------------
config = DEFAULT_CONFIG.copy()
command_history = []
last_results = {}
active_monitoring_threads = []
stop_monitoring_event = threading.Event()

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

        if levelname == "DEBUG":
            return f"{NORD9}{msg}{NC}"
        elif levelname == "INFO":
            return f"{NORD14}{msg}{NC}"
        elif levelname == "WARNING":
            return f"{NORD13}{msg}{NC}"
        elif levelname in ("ERROR", "CRITICAL"):
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
    numeric_level = getattr(logging, DEFAULT_LOG_LEVEL, logging.INFO)
    logger.setLevel(numeric_level)

    # Clear any existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    # Console handler with colors
    console_formatter = NordColorFormatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler (no colors in file)
    file_formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
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
    # Stop any ongoing monitoring
    stop_monitoring_event.set()

    # Wait for monitoring threads to complete
    for thread in active_monitoring_threads:
        if thread.is_alive():
            thread.join(timeout=1.0)

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
    save_config()
    save_history()

    # Stop any ongoing monitoring
    stop_monitoring_event.set()

    # Wait for monitoring threads to complete
    for thread in active_monitoring_threads:
        if thread.is_alive():
            thread.join(timeout=1.0)


atexit.register(cleanup)

# ------------------------------------------------------------------------------
# CONFIGURATION MANAGEMENT
# ------------------------------------------------------------------------------


def init_config_dir():
    """
    Initialize configuration directories.
    """
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)


def load_config():
    """
    Load configuration from file or create default if not exists.
    """
    global config

    init_config_dir()

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                loaded_config = json.load(f)
                # Update default config with loaded values, preserving new defaults
                for key, value in loaded_config.items():
                    if key in DEFAULT_CONFIG:
                        config[key] = value
            logging.debug("Configuration loaded from file.")
        except Exception as e:
            logging.warning(f"Error loading configuration: {e}. Using defaults.")
            config = DEFAULT_CONFIG.copy()
    else:
        logging.debug("No configuration file found. Using defaults.")
        save_config()  # Create initial config file


def save_config():
    """
    Save current configuration to file.
    """
    init_config_dir()

    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
        logging.debug("Configuration saved to file.")
    except Exception as e:
        logging.warning(f"Error saving configuration: {e}")


def load_history():
    """
    Load command history from file.
    """
    global command_history

    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                command_history = json.load(f)
                # Trim history if needed
                if len(command_history) > config["max_history"]:
                    command_history = command_history[-config["max_history"] :]
            logging.debug("Command history loaded from file.")
        except Exception as e:
            logging.warning(f"Error loading command history: {e}")
            command_history = []
    else:
        logging.debug("No command history file found.")
        command_history = []


def save_history():
    """
    Save command history to file.
    """
    init_config_dir()

    try:
        # Trim history if needed
        if len(command_history) > config["max_history"]:
            command_history = command_history[-config["max_history"] :]

        with open(HISTORY_FILE, "w") as f:
            json.dump(command_history, f, indent=4)
        logging.debug("Command history saved to file.")
    except Exception as e:
        logging.warning(f"Error saving command history: {e}")


def add_to_history(command, parameters=None):
    """
    Add a command to history with timestamp.
    """
    global command_history

    history_item = {
        "command": command,
        "parameters": parameters or {},
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    command_history.append(history_item)

    # Update recent commands in config
    if command not in config["recent_commands"]:
        config["recent_commands"].insert(0, command)
        if len(config["recent_commands"]) > 10:  # Keep only 10 most recent
            config["recent_commands"] = config["recent_commands"][:10]


def save_results(command, data, file_format="json"):
    """
    Save command results to a file.

    Args:
        command: The command that generated the results
        data: The data to save
        file_format: Format to save in ('json', 'txt', or 'csv')
    """
    if not config["autosave_results"]:
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{command}_{timestamp}.{file_format}"
    filepath = os.path.join(REPORTS_DIR, filename)

    try:
        with open(filepath, "w") as f:
            if file_format == "json":
                json.dump(data, f, indent=4)
            elif file_format == "csv":
                if isinstance(data, list) and len(data) > 0:
                    writer = csv.DictWriter(f, fieldnames=data[0].keys())
                    writer.writeheader()
                    writer.writerows(data)
                else:
                    f.write("No data or invalid format for CSV\n")
            else:  # txt
                f.write(str(data))

        logging.info(f"Results saved to: {filepath}")
        return filepath
    except Exception as e:
        logging.warning(f"Error saving results: {e}")
        return None


# ------------------------------------------------------------------------------
# DEPENDENCY CHECKING
# ------------------------------------------------------------------------------


def check_dependencies():
    """
    Check for core required dependencies.
    """
    required_commands = ["ip", "ping"]
    for cmd in required_commands:
        if not shutil.which(cmd):
            logging.error(
                f"The '{cmd}' command is not found in your PATH. Please install it and try again."
            )
            sys.exit(1)


def is_installed(cmd: str) -> bool:
    """
    Check if a specific command is installed and available in the PATH.

    Args:
        cmd: Command name to check

    Returns:
        bool: True if command exists, False otherwise
    """
    return shutil.which(cmd) is not None


def suggest_install_command(package_name: str) -> str:
    """
    Suggest an installation command based on the detected Linux distribution.

    Args:
        package_name: Name of the package to install

    Returns:
        str: Suggested installation command
    """
    distro = ""

    if os.path.exists("/etc/os-release"):
        with open("/etc/os-release", "r") as f:
            content = f.read().lower()
            if "debian" in content or "ubuntu" in content:
                return f"sudo apt install {package_name}"
            elif "fedora" in content:
                return f"sudo dnf install {package_name}"
            elif "arch" in content:
                return f"sudo pacman -S {package_name}"
            elif "opensuse" in content:
                return f"sudo zypper install {package_name}"

    # Default to apt if we couldn't determine the distribution
    return f"sudo apt install {package_name}"


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


def run_command(
    command: list,
    check=False,
    capture_output=True,
    text=True,
    color=NORD14,
    timeout=None,
    show_progress=False,
    **kwargs,
):
    """
    Execute a shell command and return/print its output.

    Args:
        command: List of command and arguments to execute
        check: Whether to raise exception on non-zero return code
        capture_output: Whether to capture stdout/stderr
        text: Whether to return text instead of bytes
        color: ANSI color for output printing
        timeout: Command timeout in seconds
        show_progress: Show progress indicator during execution
        **kwargs: Additional arguments for subprocess.run

    Returns:
        The command output or error message
    """
    command_str = " ".join(command) if isinstance(command, list) else command
    logging.debug(f"Executing command: {command_str}")

    if show_progress:
        print(f"{NORD14}Running command: {command_str}{NC}")
        print(f"{NORD9}Working...{NC}", end="", flush=True)
        progress_thread = threading.Thread(target=_progress_indicator)
        progress_thread.daemon = True
        progress_thread.start()

    try:
        result = subprocess.run(
            command,
            check=check,
            capture_output=capture_output,
            text=text,
            timeout=timeout,
            **kwargs,
        )

        if show_progress:
            print("\r" + " " * 20 + "\r", end="", flush=True)  # Clear progress

        output = result.stdout.strip() if capture_output else ""
        if output and color:
            print(f"{color}{output}{NC}")

        return output
    except subprocess.TimeoutExpired:
        if show_progress:
            print("\r" + " " * 20 + "\r", end="", flush=True)  # Clear progress
        logging.warning(f"Command timed out after {timeout} seconds: {command_str}")
        print(f"{NORD13}Command timed out after {timeout} seconds{NC}")
        return ""
    except subprocess.CalledProcessError as e:
        if show_progress:
            print("\r" + " " * 20 + "\r", end="", flush=True)  # Clear progress
        logging.warning(f"Command failed with exit code {e.returncode}: {command_str}")
        if e.stdout:
            print(f"{color}{e.stdout.strip()}{NC}")
        if e.stderr:
            print(f"{NORD11}{e.stderr.strip()}{NC}")
        return e.stdout if e.stdout else ""
    except Exception as e:
        if show_progress:
            print("\r" + " " * 20 + "\r", end="", flush=True)  # Clear progress
        logging.error(f"Error executing command {command_str}: {e}")
        return ""


def _progress_indicator():
    """Display a spinning progress indicator."""
    chars = ["|", "/", "-", "\\"]
    i = 0
    try:
        while True:
            print(f"\r{NORD9}Working... {chars[i]}{NC}", end="", flush=True)
            i = (i + 1) % len(chars)
            time.sleep(0.1)
    except:
        pass


def prompt_enter():
    """
    Wait for user to press Enter before continuing.
    """
    input(f"{NORD8}Press Enter to continue...{NC}")


def print_header():
    """
    Clear the screen and print the main header.
    """
    os.system("clear")
    print(
        f"{NORD8}{BOLD}┌─────────────────────────────────────────────────────────┐{NC}"
    )
    print(
        f"{NORD8}{BOLD}│         ENHANCED ADVANCED NETWORK TOOLKIT v3.0.0        │{NC}"
    )
    print(
        f"{NORD8}{BOLD}└─────────────────────────────────────────────────────────┘{NC}"
    )
    print("")
    print_section("MAIN MENU")


def print_table(headers, data, colors=None):
    """
    Print a formatted table with colored headers and data.

    Args:
        headers: List of column headers
        data: List of rows (each row is a list of values)
        colors: Optional dict mapping column indices to color codes
    """
    if not data:
        print(f"{NORD13}No data to display{NC}")
        return

    if not colors:
        colors = {}

    # Calculate column widths
    col_widths = [len(h) for h in headers]
    for row in data:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(str(cell)))

    # Print header
    header_row = "│ "
    for i, header in enumerate(headers):
        header_row += f"{NORD8}{BOLD}{header.ljust(col_widths[i])}{NC} │ "
    separator = "┌─" + "─┬─".join("─" * width for width in col_widths) + "─┐"
    bottom_sep = "└─" + "─┴─".join("─" * width for width in col_widths) + "─┘"
    mid_sep = "├─" + "─┼─".join("─" * width for width in col_widths) + "─┤"

    print(separator)
    print(header_row)
    print(mid_sep)

    # Print data rows
    for row in data:
        data_row = "│ "
        for i, cell in enumerate(row):
            if i < len(col_widths):
                cell_str = str(cell).ljust(col_widths[i])
                color = colors.get(i, NC)
                data_row += f"{color}{cell_str}{NC} │ "
        print(data_row)

    print(bottom_sep)


def get_interfaces():
    """
    Get a list of network interfaces.

    Returns:
        List of interface names
    """
    interfaces = []
    try:
        output = run_command(
            ["ip", "-o", "link", "show"], capture_output=True, text=True
        )
        for line in output.splitlines():
            match = re.search(r"^\d+:\s+([^:@]+)", line)
            if match and match.group(1) != "lo":
                interfaces.append(match.group(1))
    except Exception as e:
        logging.error(f"Error getting network interfaces: {e}")

    return interfaces


def select_interface():
    """
    Prompt user to select a network interface.

    Returns:
        Selected interface name or None if canceled
    """
    interfaces = get_interfaces()

    if not interfaces:
        print(f"{NORD11}No network interfaces found.{NC}")
        return None

    if len(interfaces) == 1:
        print(f"{NORD14}Using the only available interface: {interfaces[0]}{NC}")
        return interfaces[0]

    # If default interface is set and valid, use it
    if config["default_interface"] and config["default_interface"] in interfaces:
        print(f"{NORD14}Using default interface: {config['default_interface']}{NC}")
        return config["default_interface"]

    print(f"{NORD8}Available network interfaces:{NC}")
    for i, iface in enumerate(interfaces):
        print(f"{NORD10}[{i + 1}]{NC} {iface}")

    while True:
        choice = input(
            f"{NORD8}Select interface (1-{len(interfaces)}, or 'q' to cancel): {NC}"
        ).strip()
        if choice.lower() == "q":
            return None

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(interfaces):
                return interfaces[idx]
        except ValueError:
            pass

        print(f"{NORD13}Invalid selection. Please try again.{NC}")


def get_interface_info(interface):
    """
    Get detailed information about a network interface.

    Args:
        interface: Interface name

    Returns:
        Dict with interface information
    """
    info = {"name": interface, "addresses": []}

    # Get interface status
    try:
        output = run_command(
            ["ip", "link", "show", interface], capture_output=True, text=True
        )
        if "state UP" in output:
            info["status"] = "UP"
        elif "state DOWN" in output:
            info["status"] = "DOWN"
        else:
            info["status"] = "UNKNOWN"

        # Get MAC address
        match = re.search(r"link/\w+\s+([0-9a-fA-F:]+)", output)
        if match:
            info["mac"] = match.group(1)
    except Exception as e:
        logging.error(f"Error getting interface link info: {e}")

    # Get IP addresses
    try:
        output = run_command(
            ["ip", "addr", "show", interface], capture_output=True, text=True
        )
        for line in output.splitlines():
            # IPv4
            match = re.search(r"inet\s+([0-9.]+/\d+)", line)
            if match:
                info["addresses"].append({"type": "IPv4", "address": match.group(1)})

            # IPv6
            match = re.search(r"inet6\s+([0-9a-fA-F:]+/\d+)", line)
            if match and not match.group(1).startswith("fe80"):  # Skip link-local
                info["addresses"].append({"type": "IPv6", "address": match.group(1)})
    except Exception as e:
        logging.error(f"Error getting interface IP info: {e}")

    # Get interface statistics
    try:
        with open(f"/sys/class/net/{interface}/statistics/rx_bytes", "r") as f:
            info["rx_bytes"] = int(f.read().strip())
        with open(f"/sys/class/net/{interface}/statistics/tx_bytes", "r") as f:
            info["tx_bytes"] = int(f.read().strip())
    except Exception as e:
        logging.debug(f"Could not read interface statistics: {e}")

    return info


def format_bytes(bytes_value, precision=2):
    """
    Format bytes to human-readable format (KB, MB, GB, etc.)

    Args:
        bytes_value: Number of bytes
        precision: Number of decimal places

    Returns:
        Formatted string
    """
    if bytes_value < 1024:
        return f"{bytes_value} B"

    units = ["KB", "MB", "GB", "TB", "PB"]
    for unit in units:
        bytes_value /= 1024
        if bytes_value < 1024:
            return f"{bytes_value:.{precision}f} {unit}"

    return f"{bytes_value:.{precision}f} {units[-1]}"


def format_mac_vendor(mac_address):
    """
    Look up the vendor of a MAC address.

    Args:
        mac_address: MAC address string (e.g., 00:11:22:33:44:55)

    Returns:
        Vendor name or 'Unknown'
    """
    # Extract OUI (first 3 bytes)
    mac = mac_address.replace(":", "").replace("-", "").upper()
    oui = mac[:6]

    # Path to local copy of MAC database (will be downloaded if not exists)
    mac_db_path = os.path.join(CONFIG_DIR, "mac_vendors.txt")

    # Try to load from local file
    vendor = "Unknown"
    try:
        if not os.path.exists(mac_db_path) or os.path.getsize(mac_db_path) == 0:
            # Download OUI database if not exists
            logging.info("Downloading MAC vendor database...")
            with urllib.request.urlopen(
                "http://standards-oui.ieee.org/oui.txt"
            ) as response:
                with open(mac_db_path, "wb") as out_file:
                    out_file.write(response.read())

        # Search for the OUI in the database
        with open(mac_db_path, "r", errors="ignore") as f:
            for line in f:
                if oui in line:
                    parts = line.strip().split("(hex)")
                    if len(parts) > 1:
                        vendor = parts[1].strip()
                        break
    except Exception as e:
        logging.debug(f"Error looking up MAC vendor: {e}")

    return vendor


# ------------------------------------------------------------------------------
# NETWORK CALCULATION FUNCTIONS
# ------------------------------------------------------------------------------


def subnet_calculator():
    """
    Calculate subnet information from IP and netmask/CIDR.
    """
    print_section("Subnet Calculator")
    logging.info("Calculating subnet information...")

    # Get input from user
    ip_input = input(f"{NORD8}Enter IP address (e.g., 192.168.1.1): {NC}").strip()
    mask_input = input(
        f"{NORD8}Enter netmask or CIDR (e.g., 255.255.255.0 or 24): {NC}"
    ).strip()

    # Parse inputs
    try:
        # Convert netmask to CIDR if needed
        if "." in mask_input:
            # It's a netmask (e.g., 255.255.255.0)
            mask_parts = mask_input.split(".")
            if len(mask_parts) != 4:
                raise ValueError("Invalid netmask format")

            binary = ""
            for part in mask_parts:
                binary += bin(int(part))[2:].zfill(8)

            cidr = binary.count("1")
        else:
            # It's CIDR notation (e.g., 24)
            cidr = int(mask_input)
            if cidr < 0 or cidr > 32:
                raise ValueError("CIDR must be between 0 and 32")

        # Create network object
        network = ipaddress.IPv4Network(f"{ip_input}/{cidr}", strict=False)

        # Calculate subnet information
        info = {
            "ip_address": ip_input,
            "cidr_notation": f"{network.network_address}/{network.prefixlen}",
            "netmask": str(network.netmask),
            "network_address": str(network.network_address),
            "broadcast_address": str(network.broadcast_address),
            "first_usable": str(network.network_address + 1)
            if network.prefixlen < 31
            else "N/A",
            "last_usable": str(network.broadcast_address - 1)
            if network.prefixlen < 31
            else "N/A",
            "total_hosts": network.num_addresses,
            "usable_hosts": max(0, network.num_addresses - 2)
            if network.prefixlen < 31
            else network.num_addresses,
        }

        # Display results
        print(f"\n{NORD8}{BOLD}Subnet Information:{NC}")
        print(f"{NORD14}IP Address:        {info['ip_address']}{NC}")
        print(f"{NORD14}CIDR Notation:     {info['cidr_notation']}{NC}")
        print(f"{NORD14}Netmask:           {info['netmask']}{NC}")
        print(f"{NORD14}Network Address:   {info['network_address']}{NC}")
        print(f"{NORD14}Broadcast Address: {info['broadcast_address']}{NC}")
        print(f"{NORD14}First Usable:      {info['first_usable']}{NC}")
        print(f"{NORD14}Last Usable:       {info['last_usable']}{NC}")
        print(f"{NORD14}Total Hosts:       {info['total_hosts']}{NC}")
        print(f"{NORD14}Usable Hosts:      {info['usable_hosts']}{NC}")

        # Save results
        last_results["subnet_calculator"] = info
        if config["autosave_results"]:
            save_results("subnet_calculator", info)

    except Exception as e:
        logging.error(f"Error calculating subnet information: {e}")
        print(f"{NORD11}Error: {str(e)}{NC}")

    prompt_enter()


# ------------------------------------------------------------------------------
# BASIC NETWORK INFORMATION FUNCTIONS
# ------------------------------------------------------------------------------


def show_network_interfaces(interface=None):
    """
    Display all network interfaces and their configurations.

    Args:
        interface: Optional specific interface to show
    """
    print_section("Network Interfaces")
    logging.info("Displaying network interfaces...")

    # If interface is specified, show only that one
    if interface:
        info = get_interface_info(interface)
        print(f"{NORD8}{BOLD}Interface: {info['name']}{NC}")
        print(
            f"{NORD14}Status:     {NORD11 if info['status'] == 'DOWN' else NORD14}{info['status']}{NC}"
        )

        if "mac" in info:
            vendor = format_mac_vendor(info["mac"])
            print(f"{NORD14}MAC:        {info['mac']} ({vendor}){NC}")

        if "addresses" in info:
            print(f"{NORD14}Addresses:{NC}")
            for addr in info["addresses"]:
                print(f"{NORD14}  {addr['type']}: {addr['address']}{NC}")

        if "rx_bytes" in info and "tx_bytes" in info:
            print(f"{NORD14}RX Bytes:   {format_bytes(info['rx_bytes'])}{NC}")
            print(f"{NORD14}TX Bytes:   {format_bytes(info['tx_bytes'])}{NC}")
    else:
        # Show all interfaces in a table
        interfaces = get_interfaces()

        if not interfaces:
            print(f"{NORD13}No network interfaces found.{NC}")
            prompt_enter()
            return

        table_data = []
        for iface in interfaces:
            info = get_interface_info(iface)
            ipv4 = "N/A"
            ipv6 = "N/A"

            for addr in info.get("addresses", []):
                if addr["type"] == "IPv4":
                    ipv4 = addr["address"]
                elif addr["type"] == "IPv6":
                    ipv6 = addr["address"]

            status_color = NORD11 if info.get("status") == "DOWN" else NORD14

            table_data.append(
                [
                    info["name"],
                    info.get("status", "UNKNOWN"),
                    info.get("mac", "N/A"),
                    ipv4,
                    ipv6,
                    format_bytes(info.get("rx_bytes", 0)),
                    format_bytes(info.get("tx_bytes", 0)),
                ]
            )

        headers = ["Interface", "Status", "MAC", "IPv4", "IPv6", "RX", "TX"]
        print_table(headers, table_data, {1: status_color})

    last_results["network_interfaces"] = interfaces if not interface else [interface]

    prompt_enter()


def show_routing_table():
    """
    Display the system's IP routing table.
    """
    print_section("Routing Table")
    logging.info("Displaying routing table...")

    # Get routing table (IPv4)
    ipv4_routes = []
    try:
        output = run_command(["ip", "-4", "route"], capture_output=True, text=True)
        for line in output.splitlines():
            parts = line.strip().split()
            if len(parts) >= 3:
                dest = parts[0]
                if dest == "default":
                    dest = "0.0.0.0/0"

                gateway = (
                    "direct"
                    if "dev" in parts and "via" not in parts
                    else parts[parts.index("via") + 1]
                )
                dev = parts[parts.index("dev") + 1] if "dev" in parts else "N/A"
                metric = (
                    parts[parts.index("metric") + 1] if "metric" in parts else "N/A"
                )

                ipv4_routes.append([dest, gateway, dev, metric])
    except Exception as e:
        logging.error(f"Error getting IPv4 routing table: {e}")

    # Get routing table (IPv6)
    ipv6_routes = []
    try:
        output = run_command(["ip", "-6", "route"], capture_output=True, text=True)
        for line in output.splitlines():
            parts = line.strip().split()
            if len(parts) >= 3:
                dest = parts[0]
                if dest == "default":
                    dest = "::/0"

                gateway = (
                    "direct"
                    if "dev" in parts and "via" not in parts
                    else parts[parts.index("via") + 1]
                )
                dev = parts[parts.index("dev") + 1] if "dev" in parts else "N/A"
                metric = (
                    parts[parts.index("metric") + 1] if "metric" in parts else "N/A"
                )

                ipv6_routes.append([dest, gateway, dev, metric])
    except Exception as e:
        logging.error(f"Error getting IPv6 routing table: {e}")

    # Display results
    if ipv4_routes:
        print(f"{NORD8}{BOLD}IPv4 Routing Table:{NC}")
        headers = ["Destination", "Gateway", "Interface", "Metric"]
        print_table(headers, ipv4_routes)
        print("")

    if ipv6_routes:
        print(f"{NORD8}{BOLD}IPv6 Routing Table:{NC}")
        headers = ["Destination", "Gateway", "Interface", "Metric"]
        print_table(headers, ipv6_routes)

    if not ipv4_routes and not ipv6_routes:
        print(f"{NORD13}No routing information found.{NC}")

    # Save results
    last_results["routing_table"] = {"ipv4": ipv4_routes, "ipv6": ipv6_routes}
    if config["autosave_results"]:
        save_results("routing_table", last_results["routing_table"])

    prompt_enter()


def show_arp_table():
    """
    Display the ARP (Address Resolution Protocol) table.
    """
    print_section("ARP Table")
    logging.info("Displaying ARP table...")

    # Get ARP table
    arp_entries = []
    try:
        output = run_command(["ip", "neigh", "show"], capture_output=True, text=True)
        for line in output.splitlines():
            parts = line.strip().split()
            if len(parts) >= 4:
                ip = parts[0]
                dev = parts[parts.index("dev") + 1] if "dev" in parts else "N/A"
                mac = parts[parts.index("lladdr") + 1] if "lladdr" in parts else "N/A"
                state = parts[-1]

                # Get vendor information
                vendor = format_mac_vendor(mac) if mac != "N/A" else "N/A"

                arp_entries.append([ip, mac, vendor, dev, state])
    except Exception as e:
        logging.error(f"Error getting ARP table: {e}")

    # Display results
    if arp_entries:
        headers = ["IP Address", "MAC Address", "Vendor", "Interface", "State"]
        print_table(headers, arp_entries)
    else:
        print(f"{NORD13}No ARP entries found.{NC}")

    # Save results
    last_results["arp_table"] = arp_entries
    if config["autosave_results"]:
        save_results(
            "arp_table",
            [
                {
                    "ip": e[0],
                    "mac": e[1],
                    "vendor": e[2],
                    "interface": e[3],
                    "state": e[4],
                }
                for e in arp_entries
            ],
        )

    prompt_enter()


def show_network_statistics():
    """
    Display detailed network statistics.
    """
    print_section("Network Statistics")
    logging.info("Displaying network statistics...")

    # Get network statistics from /proc/net/dev
    interface_stats = []
    try:
        with open("/proc/net/dev", "r") as f:
            lines = f.readlines()

            # Skip the header lines
            for line in lines[2:]:
                parts = line.strip().split(":")
                if len(parts) >= 2:
                    iface = parts[0].strip()
                    if iface != "lo":  # Skip loopback
                        values = parts[1].strip().split()
                        if len(values) >= 16:
                            rx_bytes = int(values[0])
                            rx_packets = int(values[1])
                            rx_errors = int(values[2])
                            rx_dropped = int(values[3])

                            tx_bytes = int(values[8])
                            tx_packets = int(values[9])
                            tx_errors = int(values[10])
                            tx_dropped = int(values[11])

                            interface_stats.append(
                                [
                                    iface,
                                    format_bytes(rx_bytes),
                                    rx_packets,
                                    rx_errors,
                                    rx_dropped,
                                    format_bytes(tx_bytes),
                                    tx_packets,
                                    tx_errors,
                                    tx_dropped,
                                ]
                            )
    except Exception as e:
        logging.error(f"Error getting network statistics: {e}")

    # Display results
    if interface_stats:
        headers = [
            "Interface",
            "RX Bytes",
            "RX Packets",
            "RX Errors",
            "RX Dropped",
            "TX Bytes",
            "TX Packets",
            "TX Errors",
            "TX Dropped",
        ]
        print_table(headers, interface_stats)
    else:
        print(f"{NORD13}No network statistics available.{NC}")

    # Save results
    last_results["network_statistics"] = interface_stats
    if config["autosave_results"]:
        data = []
        for stat in interface_stats:
            data.append(
                {
                    "interface": stat[0],
                    "rx_bytes": stat[1],
                    "rx_packets": stat[2],
                    "rx_errors": stat[3],
                    "rx_dropped": stat[4],
                    "tx_bytes": stat[5],
                    "tx_packets": stat[6],
                    "tx_errors": stat[7],
                    "tx_dropped": stat[8],
                }
            )
        save_results("network_statistics", data)

    prompt_enter()


def show_listening_ports():
    """
    Display all listening TCP and UDP ports.
    """
    print_section("Listening Ports")
    logging.info("Displaying listening ports...")

    has_netstat = is_installed("netstat")
    has_ss = is_installed("ss")

    if not has_netstat and not has_ss:
        print(
            f"{NORD13}Neither 'netstat' nor 'ss' is installed. Please install one of them.{NC}"
        )
        prompt_enter()
        return

    # Prefer ss over netstat as it's more modern
    cmd_tool = "ss" if has_ss else "netstat"

    # Get TCP listening ports
    tcp_ports = []
    try:
        if cmd_tool == "ss":
            output = run_command(["ss", "-tlnp"], capture_output=True, text=True)
            for line in output.splitlines()[1:]:  # Skip header
                parts = line.strip().split()
                if len(parts) >= 5:
                    state = parts[0]
                    if state == "LISTEN":
                        addr = parts[4]
                        process = parts[6] if len(parts) > 6 else "N/A"

                        # Extract local address and port
                        if ":" in addr:
                            ip, port = addr.rsplit(":", 1)
                            # Clean up IPv6 address format
                            if ip.startswith("[") and ip.endswith("]"):
                                ip = ip[1:-1]
                            tcp_ports.append(["TCP", port, ip, process])
        else:  # netstat
            output = run_command(["netstat", "-tlnp"], capture_output=True, text=True)
            for line in output.splitlines()[2:]:  # Skip headers
                parts = line.strip().split()
                if len(parts) >= 6 and parts[5] == "LISTEN":
                    proto = parts[0]
                    if proto in ["tcp", "tcp6"]:
                        addr = parts[3]
                        process = parts[6] if len(parts) > 6 else "N/A"

                        # Extract local address and port
                        if ":" in addr:
                            ip, port = addr.rsplit(":", 1)
                            # Clean up IPv6 address format
                            if ip.startswith("[") and ip.endswith("]"):
                                ip = ip[1:-1]
                            tcp_ports.append(["TCP", port, ip, process])
    except Exception as e:
        logging.error(f"Error getting TCP listening ports: {e}")

    # Get UDP listening ports
    udp_ports = []
    try:
        if cmd_tool == "ss":
            output = run_command(["ss", "-ulnp"], capture_output=True, text=True)
            for line in output.splitlines()[1:]:  # Skip header
                parts = line.strip().split()
                if len(parts) >= 5:
                    addr = parts[4]
                    process = parts[6] if len(parts) > 6 else "N/A"

                    # Extract local address and port
                    if ":" in addr:
                        ip, port = addr.rsplit(":", 1)
                        # Clean up IPv6 address format
                        if ip.startswith("[") and ip.endswith("]"):
                            ip = ip[1:-1]
                        udp_ports.append(["UDP", port, ip, process])
        else:  # netstat
            output = run_command(["netstat", "-ulnp"], capture_output=True, text=True)
            for line in output.splitlines()[2:]:  # Skip headers
                parts = line.strip().split()
                if len(parts) >= 6:
                    proto = parts[0]
                    if proto in ["udp", "udp6"]:
                        addr = parts[3]
                        process = parts[6] if len(parts) > 6 else "N/A"

                        # Extract local address and port
                        if ":" in addr:
                            ip, port = addr.rsplit(":", 1)
                            # Clean up IPv6 address format
                            if ip.startswith("[") and ip.endswith("]"):
                                ip = ip[1:-1]
                            udp_ports.append(["UDP", port, ip, process])
    except Exception as e:
        logging.error(f"Error getting UDP listening ports: {e}")

    # Combine and sort by port number
    all_ports = tcp_ports + udp_ports
    all_ports.sort(key=lambda x: int(x[1]))

    # Display results
    if all_ports:
        headers = ["Protocol", "Port", "Local Address", "Process"]
        print_table(headers, all_ports)
    else:
        print(f"{NORD13}No listening ports found.{NC}")

    # Save results
    last_results["listening_ports"] = all_ports
    if config["autosave_results"]:
        data = []
        for port in all_ports:
            data.append(
                {
                    "protocol": port[0],
                    "port": port[1],
                    "local_address": port[2],
                    "process": port[3],
                }
            )
        save_results("listening_ports", data)

    prompt_enter()


# ------------------------------------------------------------------------------
# CONNECTIVITY TEST FUNCTIONS
# ------------------------------------------------------------------------------


def ping_test(target=None, count=None):
    """
    Perform ICMP ping test to a specified target.

    Args:
        target: Optional target hostname or IP
        count: Optional ping count
    """
    print_section("Ping Test")

    # Get target from user if not provided
    if not target:
        # Show recent hosts for selection
        if config["favorite_hosts"]:
            print(f"{NORD8}Favorite hosts:{NC}")
            for i, host in enumerate(config["favorite_hosts"]):
                print(f"{NORD10}[{i + 1}]{NC} {host}")
            print("")

        target = input(
            f"{NORD8}Enter target hostname or IP for ping test: {NC}"
        ).strip()

        # Check if it's a selection from favorites
        if (
            target.isdigit()
            and config["favorite_hosts"]
            and 1 <= int(target) <= len(config["favorite_hosts"])
        ):
            target = config["favorite_hosts"][int(target) - 1]

    if not target:
        print(f"{NORD13}No target specified. Aborting ping test.{NC}")
        prompt_enter()
        return

    # Ask for ping count if not provided
    if not count:
        count_input = input(
            f"{NORD8}Enter count (default {config['ping_count']}): {NC}"
        ).strip()
        count = int(count_input) if count_input.isdigit() else config["ping_count"]

    # Ask if we should save this host to favorites
    if target not in config["favorite_hosts"]:
        save_to_favorites = (
            input(f"{NORD8}Save this host to favorites? (y/n): {NC}").strip().lower()
        )
        if save_to_favorites == "y":
            config["favorite_hosts"].append(target)
            save_config()
            print(f"{NORD14}Host added to favorites.{NC}")

    logging.info(f"Pinging {target} for {count} packets...")

    # Determine interface (if specified)
    interface_str = ""
    interface = None
    use_specific_interface = (
        input(f"{NORD8}Use specific interface? (y/n, default n): {NC}").strip().lower()
    )
    if use_specific_interface == "y":
        interface = select_interface()
        if interface:
            interface_str = f"-I {interface}"

    # Choose packet size
    size_input = input(
        f"{NORD8}Enter packet size in bytes (default {config['packet_size']}): {NC}"
    ).strip()
    size = int(size_input) if size_input.isdigit() else config["packet_size"]

    # Build and run command
    cmd = f"ping -c {count} -s {size} {interface_str} {target}"
    output = run_command(cmd.split(), show_progress=True)

    # Parse results
    results = {
        "target": target,
        "count": count,
        "size": size,
        "interface": interface,
        "packets_sent": 0,
        "packets_received": 0,
        "packet_loss": "100%",
        "min_rtt": "N/A",
        "avg_rtt": "N/A",
        "max_rtt": "N/A",
        "mdev_rtt": "N/A",
    }

    for line in output.splitlines():
        # Extract packet statistics
        if "packets transmitted" in line:
            match = re.search(r"(\d+) packets transmitted, (\d+) received", line)
            if match:
                results["packets_sent"] = int(match.group(1))
                results["packets_received"] = int(match.group(2))

        # Extract packet loss
        if "packet loss" in line:
            match = re.search(r"(\d+)% packet loss", line)
            if match:
                results["packet_loss"] = f"{match.group(1)}%"

        # Extract round-trip time statistics
        if "min/avg/max" in line:
            match = re.search(
                r"min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)", line
            )
            if match:
                results["min_rtt"] = f"{match.group(1)} ms"
                results["avg_rtt"] = f"{match.group(2)} ms"
                results["max_rtt"] = f"{match.group(3)} ms"
                results["mdev_rtt"] = f"{match.group(4)} ms"

    # Save results
    last_results["ping_test"] = results
    if config["autosave_results"]:
        save_results("ping_test", results)

    # Add to history
    add_to_history(
        "ping_test",
        {"target": target, "count": count, "size": size, "interface": interface},
    )

    prompt_enter()


def traceroute_test(target=None, max_hops=None):
    """
    Perform traceroute to measure network path and latency to a target.

    Args:
        target: Optional target hostname or IP
        max_hops: Optional maximum hop count
    """
    print_section("Traceroute Test")

    # Determine which traceroute program to use
    trace_cmd = None
    if is_installed("traceroute"):
        trace_cmd = "traceroute"
    elif is_installed("tracepath"):
        trace_cmd = "tracepath"

    if not trace_cmd:
        print(f"{NORD13}Neither traceroute nor tracepath is installed.{NC}")
        print(f"{NORD13}Please install one using:{NC}")
        print(f"{NORD14}  {suggest_install_command('traceroute')}{NC}")
        prompt_enter()
        return

    # Get target from user if not provided
    if not target:
        # Show recent hosts for selection
        if config["favorite_hosts"]:
            print(f"{NORD8}Favorite hosts:{NC}")
            for i, host in enumerate(config["favorite_hosts"]):
                print(f"{NORD10}[{i + 1}]{NC} {host}")
            print("")

        target = input(
            f"{NORD8}Enter target hostname or IP for traceroute: {NC}"
        ).strip()

        # Check if it's a selection from favorites
        if (
            target.isdigit()
            and config["favorite_hosts"]
            and 1 <= int(target) <= len(config["favorite_hosts"])
        ):
            target = config["favorite_hosts"][int(target) - 1]

    if not target:
        print(f"{NORD13}No target specified. Aborting traceroute test.{NC}")
        prompt_enter()
        return

    # Ask for max hops if not provided
    if not max_hops:
        max_hops_input = input(
            f"{NORD8}Enter maximum hops (default {config['traceroute_max_hops']}): {NC}"
        ).strip()
        max_hops = (
            int(max_hops_input)
            if max_hops_input.isdigit()
            else config["traceroute_max_hops"]
        )

    # Ask if we should save this host to favorites
    if target not in config["favorite_hosts"]:
        save_to_favorites = (
            input(f"{NORD8}Save this host to favorites? (y/n): {NC}").strip().lower()
        )
        if save_to_favorites == "y":
            config["favorite_hosts"].append(target)
            save_config()
            print(f"{NORD14}Host added to favorites.{NC}")

    logging.info(f"Performing traceroute to {target} with max {max_hops} hops...")

    # Build command based on program
    cmd = None
    if trace_cmd == "traceroute":
        cmd = ["traceroute", "-m", str(max_hops), target]
    else:  # tracepath
        cmd = ["tracepath", "-m", str(max_hops), target]

    # Run traceroute
    output = run_command(cmd, show_progress=True)

    # Parse results
    hops = []
    for line in output.splitlines():
        if trace_cmd == "traceroute":
            match = re.search(r"^\s*(\d+)\s+([\w\.-]+|\*)\s+(.*)", line)
            if match:
                hop_num = match.group(1)
                hop_host = match.group(2)
                hop_times = match.group(3)

                # Parse multiple time measurements
                times = re.findall(r"([\d.]+) ms", hop_times)
                avg_time = "N/A"
                if times:
                    avg_time = f"{sum(float(t) for t in times) / len(times):.2f} ms"

                hops.append(
                    {
                        "hop": hop_num,
                        "host": hop_host,
                        "avg_time": avg_time,
                        "raw_times": hop_times,
                    }
                )
        else:  # tracepath
            match = re.search(r"^\s*(\d+):\s+([\w\.-]+|\?)\s+(.*)", line)
            if match:
                hop_num = match.group(1)
                hop_host = match.group(2)
                hop_info = match.group(3)

                # Extract time if available
                time_match = re.search(r"([\d.]+)ms", hop_info)
                time = time_match.group(1) + " ms" if time_match else "N/A"

                hops.append(
                    {
                        "hop": hop_num,
                        "host": hop_host,
                        "avg_time": time,
                        "raw_times": hop_info,
                    }
                )

    # Save results
    last_results["traceroute_test"] = {
        "target": target,
        "max_hops": max_hops,
        "hops": hops,
    }
    if config["autosave_results"]:
        save_results("traceroute_test", last_results["traceroute_test"])

    # Add to history
    add_to_history("traceroute_test", {"target": target, "max_hops": max_hops})

    prompt_enter()


# ------------------------------------------------------------------------------
# MAIN MENU FUNCTIONS
# ------------------------------------------------------------------------------


def basic_menu():
    """
    Display and handle the basic network information menu.
    """
    while True:
        print_header()
        logging.info("Basic Network Information:")
        print(f"{NORD10}[1]{NC} Show Network Interfaces")
        print(f"{NORD10}[2]{NC} Show Routing Table")
        print(f"{NORD10}[3]{NC} Show ARP Table")
        print(f"{NORD10}[4]{NC} Show Network Statistics")
        print(f"{NORD10}[5]{NC} Show Listening Ports")
        print(f"{NORD10}[6]{NC} Subnet Calculator")
        print(f"{NORD10}[0]{NC} Return to Main Menu")

        opt = input(f"{NORD8}Enter your choice: {NC}").strip()
        if opt == "1":
            show_network_interfaces()
        elif opt == "2":
            show_routing_table()
        elif opt == "3":
            show_arp_table()
        elif opt == "4":
            show_network_statistics()
        elif opt == "5":
            show_listening_ports()
        elif opt == "6":
            subnet_calculator()
        elif opt == "0":
            break
        else:
            logging.warning("Invalid selection.")
            time.sleep(1)


def connectivity_menu():
    """
    Display and handle the connectivity tests menu.
    """
    while True:
        print_header()
        logging.info("Connectivity Tests:")
        print(f"{NORD10}[1]{NC} Ping Test")
        print(f"{NORD10}[2]{NC} Traceroute Test")
        print(f"{NORD10}[3]{NC} DNS Lookup")
        print(f"{NORD10}[4]{NC} SSL Certificate Check")
        print(f"{NORD10}[5]{NC} HTTP Header Analysis")
        print(f"{NORD10}[0]{NC} Return to Main Menu")

        opt = input(f"{NORD8}Enter your choice: {NC}").strip()
        if opt == "1":
            ping_test()
        elif opt == "2":
            traceroute_test()
        elif opt == "3":
            print(
                f"{NORD14}DNS Lookup function not implemented in this demo version.{NC}"
            )
            prompt_enter()
        elif opt == "4":
            print(
                f"{NORD14}SSL Certificate Check function not implemented in this demo version.{NC}"
            )
            prompt_enter()
        elif opt == "5":
            print(
                f"{NORD14}HTTP Header Analysis function not implemented in this demo version.{NC}"
            )
            prompt_enter()
        elif opt == "0":
            break
        else:
            logging.warning("Invalid selection.")
            time.sleep(1)


def main_menu():
    """
    Display and handle the main menu.
    """
    while True:
        print_header()
        logging.info("Select an option:")
        print(f"{NORD10}[1]{NC} Basic Network Information")
        print(f"{NORD10}[2]{NC} Connectivity Tests")
        print(f"{NORD10}[3]{NC} Port Scanning & Network Discovery")
        print(f"{NORD10}[4]{NC} Performance Tests")
        print(f"{NORD10}[5]{NC} Advanced / Penetration Testing Tools")
        print(f"{NORD10}[6]{NC} Extra Tools")
        print(f"{NORD10}[7]{NC} Settings")
        print(f"{NORD10}[q]{NC} Quit")

        choice = input(f"{NORD8}Enter your choice: {NC}").strip().lower()
        if choice == "1":
            basic_menu()
        elif choice == "2":
            connectivity_menu()
        elif choice == "3":
            print(
                f"{NORD14}Port Scanning & Network Discovery functions not implemented in this demo version.{NC}"
            )
            prompt_enter()
        elif choice == "4":
            print(
                f"{NORD14}Performance Tests functions not implemented in this demo version.{NC}"
            )
            prompt_enter()
        elif choice == "5":
            print(
                f"{NORD14}Advanced / Penetration Testing Tools not implemented in this demo version.{NC}"
            )
            prompt_enter()
        elif choice == "6":
            print(f"{NORD14}Extra Tools not implemented in this demo version.{NC}")
            prompt_enter()
        elif choice == "7":
            print(f"{NORD14}Settings menu not implemented in this demo version.{NC}")
            prompt_enter()
        elif choice == "q":
            logging.info("Exiting. Goodbye!")
            sys.exit(0)
        else:
            logging.warning("Invalid selection. Please choose a valid option.")
            time.sleep(1)


# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------


def main():
    """
    Main entry point for the script.
    """
    setup_logging()
    check_dependencies()

    # Check for root privileges
    check_root()

    # Set up configuration and directories
    init_config_dir()
    load_config()
    load_history()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"ENHANCED NETWORK TOOLKIT STARTED AT {now}")
    logging.info("=" * 80)

    # Display the main menu
    try:
        main_menu()
    except KeyboardInterrupt:
        logging.info("Program interrupted by user.")
    except Exception as e:
        logging.error(f"Unhandled exception: {e}")
        sys.exit(1)

    # Finish up
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"ENHANCED NETWORK TOOLKIT ENDED AT {now}")
    logging.info("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logging.error(f"Unhandled exception: {ex}")
        sys.exit(1)
