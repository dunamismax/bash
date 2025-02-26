#!/usr/bin/env python3
"""
Enhanced Network Toolkit
--------------------------
Description:
  A production-grade network toolkit that performs common and advanced network
  tests, diagnostics, performance measurements, and penetration testing tasks on
  Debian-based systems. This interactive tool features a Nord-themed user interface,
  rich progress indicators, detailed logging, and graceful signal handling.

Features include:
  - Basic network information gathering
  - Connectivity tests (ping, traceroute)
  - Network scanning and discovery
  - Subnet calculation
  - Detailed routing, ARP, and interface statistics
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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

# ------------------------------------------------------------------------------
# Environment & Configuration
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

# Default configuration dictionary
DEFAULT_CONFIG = {
    "ping_count": 5,
    "traceroute_max_hops": 30,
    "port_scan_default_range": "1-1024",
    "dns_servers": ["1.1.1.1", "8.8.8.8", "9.9.9.9"],
    "speedtest_server": None,
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
    "bandwidth_interval": 1.0,
}

# Global variables for config, history, and results
config = DEFAULT_CONFIG.copy()
command_history = []
last_results = {}
active_monitoring_threads = []
stop_monitoring_event = threading.Event()

# Rich Console for formatted output
console = Console()

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0 = "\033[38;2;46;52;64m"  # Polar Night (dark)
NORD1 = "\033[38;2;59;66;82m"  # Polar Night (darker)
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
NC = "\033[0m"  # Reset

# Text styles
BOLD = "\033[1m"
ITALIC = "\033[3m"
UNDERLINE = "\033[4m"


# ------------------------------------------------------------------------------
# CUSTOM LOGGING
# ------------------------------------------------------------------------------
class NordColorFormatter(logging.Formatter):
    """
    Custom logging formatter to apply Nord color theme.
    """

    def __init__(self, fmt=None, datefmt=None, use_colors=True):
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors and not DISABLE_COLORS

    def format(self, record):
        msg = super().format(record)
        if not self.use_colors:
            return msg
        level = record.levelname
        if level == "DEBUG":
            return f"{NORD9}{msg}{NC}"
        elif level == "INFO":
            return f"{NORD14}{msg}{NC}"
        elif level == "WARNING":
            return f"{NORD13}{msg}{NC}"
        elif level in ("ERROR", "CRITICAL"):
            return f"{NORD11}{msg}{NC}"
        return msg


def setup_logging():
    """
    Set up logging with both console (with Nord colors) and file handlers.
    """
    log_dir = os.path.dirname(LOG_FILE)
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger()
    numeric_level = getattr(logging, DEFAULT_LOG_LEVEL, logging.INFO)
    logger.setLevel(numeric_level)

    # Remove any existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    console_formatter = NordColorFormatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        use_colors=True,
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    file_formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    try:
        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logger.warning(f"Failed to set up log file {LOG_FILE}: {e}")

    return logger


def print_section(title: str):
    """
    Print a section header using Nord-themed formatting.
    """
    border = "─" * 60
    if not DISABLE_COLORS:
        logging.info(f"{NORD10}{border}{NC}")
        logging.info(f"{NORD10}  {title}{NC}")
        logging.info(f"{NORD10}{border}{NC}")
    else:
        logging.info(border)
        logging.info(f"  {title}")
        logging.info(border)


# ------------------------------------------------------------------------------
# SIGNAL HANDLING & CLEANUP
# ------------------------------------------------------------------------------
def signal_handler(signum, frame):
    """
    Gracefully handle termination signals.
    """
    logging.error(f"Received signal {signum}. Initiating cleanup...")
    stop_monitoring_event.set()
    for thread in active_monitoring_threads:
        if thread.is_alive():
            thread.join(timeout=1.0)
    cleanup()
    sys.exit(128 + signum)


for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)


def cleanup():
    """
    Execute cleanup tasks before exit.
    """
    logging.info("Performing cleanup tasks before exit.")
    save_config()
    save_history()
    stop_monitoring_event.set()
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
    Load configuration from file; if absent, use default configuration.
    """
    global config
    init_config_dir()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                loaded_config = json.load(f)
                config.update(
                    {k: loaded_config.get(k, v) for k, v in DEFAULT_CONFIG.items()}
                )
            logging.debug("Configuration loaded from file.")
        except Exception as e:
            logging.warning(f"Error loading configuration: {e}. Using defaults.")
            config = DEFAULT_CONFIG.copy()
    else:
        logging.debug("No configuration file found. Using defaults.")
        save_config()


def save_config():
    """
    Save the current configuration to file.
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
        if len(command_history) > config["max_history"]:
            command_history[:] = command_history[-config["max_history"] :]
        with open(HISTORY_FILE, "w") as f:
            json.dump(command_history, f, indent=4)
        logging.debug("Command history saved to file.")
    except Exception as e:
        logging.warning(f"Error saving command history: {e}")


def add_to_history(command, parameters=None):
    """
    Add a command execution record to history.
    """
    history_item = {
        "command": command,
        "parameters": parameters or {},
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    command_history.append(history_item)
    if command not in config["recent_commands"]:
        config["recent_commands"].insert(0, command)
        config["recent_commands"] = config["recent_commands"][:10]


def save_results(command, data, file_format="json"):
    """
    Save command results to a report file.

    Args:
        command: Name of the command
        data: Data to save
        file_format: 'json', 'csv', or 'txt'
    Returns:
        The path to the saved file or None on error.
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
                if isinstance(data, list) and data:
                    writer = csv.DictWriter(f, fieldnames=data[0].keys())
                    writer.writeheader()
                    writer.writerows(data)
                else:
                    f.write("No data or invalid format for CSV\n")
            else:
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
    Check for required system dependencies.
    """
    required_cmds = ["ip", "ping"]
    for cmd in required_cmds:
        if not shutil.which(cmd):
            logging.error(
                f"'{cmd}' command not found. Please install it and try again."
            )
            sys.exit(1)


def is_installed(cmd: str) -> bool:
    """
    Check if a command is installed.
    """
    return shutil.which(cmd) is not None


def suggest_install_command(package_name: str) -> str:
    """
    Suggest an installation command based on the current distribution.
    """
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
    return f"sudo apt install {package_name}"


# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------
def check_root():
    """
    Ensure the script is run as root.
    """
    if os.geteuid() != 0:
        logging.error("This script must be run as root.")
        sys.exit(1)
    logging.debug("Running with root privileges.")


def run_with_progress(description: str, func, *args, **kwargs):
    """
    Run a blocking function with a rich progress spinner.
    """
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            transient=True,
        ) as progress:
            task = progress.add_task(description, total=None)
            while not future.done():
                time.sleep(0.1)
                progress.refresh()
            return future.result()


def run_command(
    command,
    check=False,
    capture_output=True,
    text=True,
    timeout=None,
    show_progress=False,
    **kwargs,
):
    """
    Execute a shell command and return its output.

    If show_progress is True, a rich spinner is displayed during execution.
    """
    command_list = command if isinstance(command, list) else command.split()
    logging.debug(f"Executing command: {' '.join(command_list)}")
    if show_progress:
        result = run_with_progress(
            "Executing command...",
            subprocess.run,
            command_list,
            check=check,
            capture_output=capture_output,
            text=text,
            timeout=timeout,
            **kwargs,
        )
    else:
        result = subprocess.run(
            command_list,
            check=check,
            capture_output=capture_output,
            text=text,
            timeout=timeout,
            **kwargs,
        )
    output = result.stdout.strip() if capture_output else ""
    return output


def prompt_enter():
    """
    Wait for user to press Enter.
    """
    input(f"{NORD8}Press Enter to continue...{NC}")


def print_header():
    """
    Clear the screen and print the main header.
    """
    os.system("clear")
    console.print(
        f"{NORD8}{BOLD}┌─────────────────────────────────────────────────────────┐{NC}"
    )
    console.print(
        f"{NORD8}{BOLD}│         ENHANCED NETWORK TOOLKIT v3.0.0                 │{NC}"
    )
    console.print(
        f"{NORD8}{BOLD}└─────────────────────────────────────────────────────────┘{NC}"
    )
    print("")
    print_section("MAIN MENU")


def print_table(headers, data, colors=None):
    """
    Print a formatted table with colored headers.
    """
    if not data:
        console.print(f"{NORD13}No data to display{NC}")
        return

    if colors is None:
        colors = {}

    # Calculate column widths
    col_widths = [len(h) for h in headers]
    for row in data:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))

    header_row = (
        "│ "
        + " │ ".join(
            f"{NORD8}{BOLD}{header.ljust(col_widths[i])}{NC}"
            for i, header in enumerate(headers)
        )
        + " │"
    )
    separator = "┌─" + "─┬─".join("─" * w for w in col_widths) + "─┐"
    mid_sep = "├─" + "─┼─".join("─" * w for w in col_widths) + "─┤"
    bottom_sep = "└─" + "─┴─".join("─" * w for w in col_widths) + "┘"

    print(separator)
    print(header_row)
    print(mid_sep)
    for row in data:
        row_str = (
            "│ "
            + " │ ".join(
                f"{colors.get(i, '')}{str(cell).ljust(col_widths[i])}{NC}"
                for i, cell in enumerate(row)
            )
            + " │"
        )
        print(row_str)
    print(bottom_sep)


def get_interfaces():
    """
    Retrieve a list of network interfaces (excluding loopback).
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
        logging.error(f"Error retrieving network interfaces: {e}")
    return interfaces


def select_interface():
    """
    Prompt user to select a network interface.
    """
    interfaces = get_interfaces()
    if not interfaces:
        console.print(f"{NORD11}No network interfaces found.{NC}")
        return None
    if len(interfaces) == 1:
        console.print(
            f"{NORD14}Using the only available interface: {interfaces[0]}{NC}"
        )
        return interfaces[0]
    if config["default_interface"] in interfaces:
        console.print(
            f"{NORD14}Using default interface: {config['default_interface']}{NC}"
        )
        return config["default_interface"]
    console.print(f"{NORD8}Available network interfaces:{NC}")
    for i, iface in enumerate(interfaces):
        console.print(f"{NORD10}[{i + 1}]{NC} {iface}")
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
        console.print(f"{NORD13}Invalid selection. Please try again.{NC}")


def get_interface_info(interface):
    """
    Get detailed information about a given network interface.
    """
    info = {"name": interface, "addresses": []}
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
        match = re.search(r"link/\w+\s+([0-9a-fA-F:]+)", output)
        if match:
            info["mac"] = match.group(1)
    except Exception as e:
        logging.error(f"Error retrieving interface link info: {e}")
    try:
        output = run_command(
            ["ip", "addr", "show", interface], capture_output=True, text=True
        )
        for line in output.splitlines():
            match = re.search(r"inet\s+([0-9.]+/\d+)", line)
            if match:
                info["addresses"].append({"type": "IPv4", "address": match.group(1)})
            match = re.search(r"inet6\s+([0-9a-fA-F:]+/\d+)", line)
            if match and not match.group(1).startswith("fe80"):
                info["addresses"].append({"type": "IPv6", "address": match.group(1)})
    except Exception as e:
        logging.error(f"Error retrieving interface IP info: {e}")
    try:
        rx_path = f"/sys/class/net/{interface}/statistics/rx_bytes"
        tx_path = f"/sys/class/net/{interface}/statistics/tx_bytes"
        with open(rx_path, "r") as f:
            info["rx_bytes"] = int(f.read().strip())
        with open(tx_path, "r") as f:
            info["tx_bytes"] = int(f.read().strip())
    except Exception as e:
        logging.debug(f"Could not retrieve interface statistics: {e}")
    return info


def format_bytes(bytes_value, precision=2):
    """
    Format a byte value into a human-readable string.
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
    Look up the vendor for a given MAC address.
    """
    mac = mac_address.replace(":", "").replace("-", "").upper()
    oui = mac[:6]
    mac_db_path = os.path.join(CONFIG_DIR, "mac_vendors.txt")
    vendor = "Unknown"
    try:
        if not os.path.exists(mac_db_path) or os.path.getsize(mac_db_path) == 0:
            logging.info("Downloading MAC vendor database...")
            with urllib.request.urlopen(
                "http://standards-oui.ieee.org/oui.txt"
            ) as response:
                with open(mac_db_path, "wb") as out_file:
                    out_file.write(response.read())
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
    Calculate subnet details based on user-provided IP and netmask/CIDR.
    """
    print_section("Subnet Calculator")
    logging.info("Calculating subnet information...")
    ip_input = input(f"{NORD8}Enter IP address (e.g., 192.168.1.1): {NC}").strip()
    mask_input = input(
        f"{NORD8}Enter netmask or CIDR (e.g., 255.255.255.0 or 24): {NC}"
    ).strip()
    try:
        if "." in mask_input:
            mask_parts = mask_input.split(".")
            if len(mask_parts) != 4:
                raise ValueError("Invalid netmask format")
            binary = "".join(bin(int(part))[2:].zfill(8) for part in mask_parts)
            cidr = binary.count("1")
        else:
            cidr = int(mask_input)
            if cidr < 0 or cidr > 32:
                raise ValueError("CIDR must be between 0 and 32")
        network = ipaddress.IPv4Network(f"{ip_input}/{cidr}", strict=False)
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
        console.print(f"\n{NORD8}{BOLD}Subnet Information:{NC}")
        for key, value in info.items():
            console.print(f"{NORD14}{key.replace('_', ' ').title()}: {value}{NC}")
        last_results["subnet_calculator"] = info
        if config["autosave_results"]:
            save_results("subnet_calculator", info)
    except Exception as e:
        logging.error(f"Error calculating subnet: {e}")
        console.print(f"{NORD11}Error: {e}{NC}")
    prompt_enter()


# ------------------------------------------------------------------------------
# BASIC NETWORK INFORMATION FUNCTIONS
# ------------------------------------------------------------------------------
def show_network_interfaces(interface=None):
    """
    Display network interfaces and their configurations.
    """
    print_section("Network Interfaces")
    logging.info("Displaying network interfaces...")
    if interface:
        info = get_interface_info(interface)
        console.print(f"{NORD8}{BOLD}Interface: {info['name']}{NC}")
        status_color = NORD11 if info.get("status") == "DOWN" else NORD14
        console.print(
            f"{NORD14}Status: {status_color}{info.get('status', 'UNKNOWN')}{NC}"
        )
        if "mac" in info:
            vendor = format_mac_vendor(info["mac"])
            console.print(f"{NORD14}MAC: {info['mac']} ({vendor}){NC}")
        if info.get("addresses"):
            console.print(f"{NORD14}Addresses:{NC}")
            for addr in info["addresses"]:
                console.print(f"  {NORD14}{addr['type']}: {addr['address']}{NC}")
        if "rx_bytes" in info and "tx_bytes" in info:
            console.print(f"{NORD14}RX Bytes: {format_bytes(info['rx_bytes'])}{NC}")
            console.print(f"{NORD14}TX Bytes: {format_bytes(info['tx_bytes'])}{NC}")
    else:
        interfaces = get_interfaces()
        if not interfaces:
            console.print(f"{NORD13}No network interfaces found.{NC}")
            prompt_enter()
            return
        table_data = []
        for iface in interfaces:
            info = get_interface_info(iface)
            ipv4 = next(
                (
                    addr["address"]
                    for addr in info.get("addresses", [])
                    if addr["type"] == "IPv4"
                ),
                "N/A",
            )
            ipv6 = next(
                (
                    addr["address"]
                    for addr in info.get("addresses", [])
                    if addr["type"] == "IPv6"
                ),
                "N/A",
            )
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
    Display the system's routing table for both IPv4 and IPv6.
    """
    print_section("Routing Table")
    logging.info("Displaying routing table...")
    ipv4_routes, ipv6_routes = [], []
    try:
        output = run_command(["ip", "-4", "route"], capture_output=True, text=True)
        for line in output.splitlines():
            parts = line.strip().split()
            if parts:
                dest = "0.0.0.0/0" if parts[0] == "default" else parts[0]
                gateway = parts[parts.index("via") + 1] if "via" in parts else "direct"
                dev = parts[parts.index("dev") + 1] if "dev" in parts else "N/A"
                metric = (
                    parts[parts.index("metric") + 1] if "metric" in parts else "N/A"
                )
                ipv4_routes.append([dest, gateway, dev, metric])
    except Exception as e:
        logging.error(f"Error retrieving IPv4 routing table: {e}")
    try:
        output = run_command(["ip", "-6", "route"], capture_output=True, text=True)
        for line in output.splitlines():
            parts = line.strip().split()
            if parts:
                dest = "::/0" if parts[0] == "default" else parts[0]
                gateway = parts[parts.index("via") + 1] if "via" in parts else "direct"
                dev = parts[parts.index("dev") + 1] if "dev" in parts else "N/A"
                metric = (
                    parts[parts.index("metric") + 1] if "metric" in parts else "N/A"
                )
                ipv6_routes.append([dest, gateway, dev, metric])
    except Exception as e:
        logging.error(f"Error retrieving IPv6 routing table: {e}")
    if ipv4_routes:
        console.print(f"{NORD8}{BOLD}IPv4 Routing Table:{NC}")
        print_table(["Destination", "Gateway", "Interface", "Metric"], ipv4_routes)
        print("")
    if ipv6_routes:
        console.print(f"{NORD8}{BOLD}IPv6 Routing Table:{NC}")
        print_table(["Destination", "Gateway", "Interface", "Metric"], ipv6_routes)
    if not ipv4_routes and not ipv6_routes:
        console.print(f"{NORD13}No routing information found.{NC}")
    last_results["routing_table"] = {"ipv4": ipv4_routes, "ipv6": ipv6_routes}
    if config["autosave_results"]:
        save_results("routing_table", last_results["routing_table"])
    prompt_enter()


def show_arp_table():
    """
    Display the ARP table.
    """
    print_section("ARP Table")
    logging.info("Displaying ARP table...")
    arp_entries = []
    try:
        output = run_command(["ip", "neigh", "show"], capture_output=True, text=True)
        for line in output.splitlines():
            parts = line.strip().split()
            if len(parts) >= 4:
                ip_addr = parts[0]
                dev = parts[parts.index("dev") + 1] if "dev" in parts else "N/A"
                mac = parts[parts.index("lladdr") + 1] if "lladdr" in parts else "N/A"
                state = parts[-1]
                vendor = format_mac_vendor(mac) if mac != "N/A" else "N/A"
                arp_entries.append([ip_addr, mac, vendor, dev, state])
    except Exception as e:
        logging.error(f"Error retrieving ARP table: {e}")
    if arp_entries:
        print_table(
            ["IP Address", "MAC Address", "Vendor", "Interface", "State"], arp_entries
        )
    else:
        console.print(f"{NORD13}No ARP entries found.{NC}")
    last_results["arp_table"] = arp_entries
    if config["autosave_results"]:
        save_results(
            "arp_table",
            [
                {
                    "ip": entry[0],
                    "mac": entry[1],
                    "vendor": entry[2],
                    "interface": entry[3],
                    "state": entry[4],
                }
                for entry in arp_entries
            ],
        )
    prompt_enter()


def show_network_statistics():
    """
    Display detailed network statistics from /proc/net/dev.
    """
    print_section("Network Statistics")
    logging.info("Displaying network statistics...")
    interface_stats = []
    try:
        with open("/proc/net/dev", "r") as f:
            lines = f.readlines()[2:]
            for line in lines:
                if ":" in line:
                    iface, data = line.split(":", 1)
                    iface = iface.strip()
                    if iface == "lo":
                        continue
                    values = data.split()
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
        logging.error(f"Error retrieving network statistics: {e}")
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
        console.print(f"{NORD13}No network statistics available.{NC}")
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
    if not (is_installed("netstat") or is_installed("ss")):
        console.print(
            f"{NORD13}Neither 'netstat' nor 'ss' is installed. Please install one.{NC}"
        )
        prompt_enter()
        return
    cmd_tool = "ss" if is_installed("ss") else "netstat"
    tcp_ports, udp_ports = [], []
    try:
        if cmd_tool == "ss":
            output = run_command(["ss", "-tlnp"], capture_output=True, text=True)
            for line in output.splitlines()[1:]:
                parts = line.split()
                if parts and parts[0] == "LISTEN":
                    addr = parts[4]
                    process = parts[6] if len(parts) > 6 else "N/A"
                    if ":" in addr:
                        ip, port = addr.rsplit(":", 1)
                        if ip.startswith("[") and ip.endswith("]"):
                            ip = ip[1:-1]
                        tcp_ports.append(["TCP", port, ip, process])
        else:
            output = run_command(["netstat", "-tlnp"], capture_output=True, text=True)
            for line in output.splitlines()[2:]:
                parts = line.split()
                if len(parts) >= 6 and parts[5] == "LISTEN":
                    proto = parts[0]
                    if proto in ["tcp", "tcp6"]:
                        addr = parts[3]
                        process = parts[6] if len(parts) > 6 else "N/A"
                        if ":" in addr:
                            ip, port = addr.rsplit(":", 1)
                            if ip.startswith("[") and ip.endswith("]"):
                                ip = ip[1:-1]
                            tcp_ports.append(["TCP", port, ip, process])
    except Exception as e:
        logging.error(f"Error retrieving TCP listening ports: {e}")
    try:
        if cmd_tool == "ss":
            output = run_command(["ss", "-ulnp"], capture_output=True, text=True)
            for line in output.splitlines()[1:]:
                parts = line.split()
                if parts:
                    addr = parts[4]
                    process = parts[6] if len(parts) > 6 else "N/A"
                    if ":" in addr:
                        ip, port = addr.rsplit(":", 1)
                        if ip.startswith("[") and ip.endswith("]"):
                            ip = ip[1:-1]
                        udp_ports.append(["UDP", port, ip, process])
        else:
            output = run_command(["netstat", "-ulnp"], capture_output=True, text=True)
            for line in output.splitlines()[2:]:
                parts = line.split()
                if len(parts) >= 6:
                    proto = parts[0]
                    if proto in ["udp", "udp6"]:
                        addr = parts[3]
                        process = parts[6] if len(parts) > 6 else "N/A"
                        if ":" in addr:
                            ip, port = addr.rsplit(":", 1)
                            if ip.startswith("[") and ip.endswith("]"):
                                ip = ip[1:-1]
                            udp_ports.append(["UDP", port, ip, process])
    except Exception as e:
        logging.error(f"Error retrieving UDP listening ports: {e}")
    all_ports = tcp_ports + udp_ports
    all_ports.sort(key=lambda x: int(x[1]))
    if all_ports:
        headers = ["Protocol", "Port", "Local Address", "Process"]
        print_table(headers, all_ports)
    else:
        console.print(f"{NORD13}No listening ports found.{NC}")
    last_results["listening_ports"] = all_ports
    if config["autosave_results"]:
        data = [
            {"protocol": p[0], "port": p[1], "local_address": p[2], "process": p[3]}
            for p in all_ports
        ]
        save_results("listening_ports", data)
    prompt_enter()


# ------------------------------------------------------------------------------
# CONNECTIVITY TEST FUNCTIONS
# ------------------------------------------------------------------------------
def ping_test(target=None, count=None):
    """
    Perform an ICMP ping test to a specified target.
    """
    print_section("Ping Test")
    if not target:
        if config["favorite_hosts"]:
            console.print(f"{NORD8}Favorite hosts:{NC}")
            for i, host in enumerate(config["favorite_hosts"]):
                console.print(f"{NORD10}[{i + 1}]{NC} {host}")
        target = input(
            f"{NORD8}Enter target hostname or IP for ping test: {NC}"
        ).strip()
        if (
            target.isdigit()
            and config["favorite_hosts"]
            and 1 <= int(target) <= len(config["favorite_hosts"])
        ):
            target = config["favorite_hosts"][int(target) - 1]
    if not target:
        console.print(f"{NORD13}No target specified. Aborting ping test.{NC}")
        prompt_enter()
        return
    if not count:
        count_input = input(
            f"{NORD8}Enter count (default {config['ping_count']}): {NC}"
        ).strip()
        count = int(count_input) if count_input.isdigit() else config["ping_count"]
    if target not in config["favorite_hosts"]:
        save_fav = (
            input(f"{NORD8}Save this host to favorites? (y/n): {NC}").strip().lower()
        )
        if save_fav == "y":
            config["favorite_hosts"].append(target)
            save_config()
            console.print(f"{NORD14}Host added to favorites.{NC}")
    logging.info(f"Pinging {target} for {count} packets...")
    interface_str = ""
    interface = None
    if (
        input(f"{NORD8}Use specific interface? (y/n, default n): {NC}").strip().lower()
        == "y"
    ):
        interface = select_interface()
        if interface:
            interface_str = f"-I {interface}"
    size_input = input(
        f"{NORD8}Enter packet size in bytes (default {config['packet_size']}): {NC}"
    ).strip()
    size = int(size_input) if size_input.isdigit() else config["packet_size"]
    cmd = f"ping -c {count} -s {size} {interface_str} {target}"
    output = run_command(cmd, show_progress=True)
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
        if "packets transmitted" in line:
            match = re.search(r"(\d+) packets transmitted, (\d+) received", line)
            if match:
                results["packets_sent"] = int(match.group(1))
                results["packets_received"] = int(match.group(2))
        if "packet loss" in line:
            match = re.search(r"(\d+)% packet loss", line)
            if match:
                results["packet_loss"] = f"{match.group(1)}%"
        if "min/avg/max" in line:
            match = re.search(
                r"min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)", line
            )
            if match:
                results["min_rtt"] = f"{match.group(1)} ms"
                results["avg_rtt"] = f"{match.group(2)} ms"
                results["max_rtt"] = f"{match.group(3)} ms"
                results["mdev_rtt"] = f"{match.group(4)} ms"
    last_results["ping_test"] = results
    if config["autosave_results"]:
        save_results("ping_test", results)
    add_to_history(
        "ping_test",
        {"target": target, "count": count, "size": size, "interface": interface},
    )
    prompt_enter()


def traceroute_test(target=None, max_hops=None):
    """
    Perform a traceroute test to measure network path and latency.
    """
    print_section("Traceroute Test")
    trace_cmd = None
    if is_installed("traceroute"):
        trace_cmd = "traceroute"
    elif is_installed("tracepath"):
        trace_cmd = "tracepath"
    if not trace_cmd:
        console.print(f"{NORD13}Neither traceroute nor tracepath is installed.{NC}")
        console.print(
            f"{NORD13}Please install using: {NORD14}{suggest_install_command('traceroute')}{NC}"
        )
        prompt_enter()
        return
    if not target:
        if config["favorite_hosts"]:
            console.print(f"{NORD8}Favorite hosts:{NC}")
            for i, host in enumerate(config["favorite_hosts"]):
                console.print(f"{NORD10}[{i + 1}]{NC} {host}")
        target = input(
            f"{NORD8}Enter target hostname or IP for traceroute: {NC}"
        ).strip()
        if (
            target.isdigit()
            and config["favorite_hosts"]
            and 1 <= int(target) <= len(config["favorite_hosts"])
        ):
            target = config["favorite_hosts"][int(target) - 1]
    if not target:
        console.print(f"{NORD13}No target specified. Aborting traceroute test.{NC}")
        prompt_enter()
        return
    if not max_hops:
        max_input = input(
            f"{NORD8}Enter maximum hops (default {config['traceroute_max_hops']}): {NC}"
        ).strip()
        max_hops = (
            int(max_input) if max_input.isdigit() else config["traceroute_max_hops"]
        )
    if target not in config["favorite_hosts"]:
        save_fav = (
            input(f"{NORD8}Save this host to favorites? (y/n): {NC}").strip().lower()
        )
        if save_fav == "y":
            config["favorite_hosts"].append(target)
            save_config()
            console.print(f"{NORD14}Host added to favorites.{NC}")
    logging.info(f"Performing traceroute to {target} with max {max_hops} hops...")
    if trace_cmd == "traceroute":
        cmd = ["traceroute", "-m", str(max_hops), target]
    else:
        cmd = ["tracepath", "-m", str(max_hops), target]
    output = run_command(cmd, show_progress=True)
    hops = []
    for line in output.splitlines():
        if trace_cmd == "traceroute":
            match = re.search(r"^\s*(\d+)\s+([\w\.-]+|\*)\s+(.*)", line)
            if match:
                hop_num = match.group(1)
                hop_host = match.group(2)
                hop_times = match.group(3)
                times = re.findall(r"([\d.]+) ms", hop_times)
                avg_time = (
                    f"{sum(float(t) for t in times) / len(times):.2f} ms"
                    if times
                    else "N/A"
                )
                hops.append(
                    {
                        "hop": hop_num,
                        "host": hop_host,
                        "avg_time": avg_time,
                        "raw_times": hop_times,
                    }
                )
        else:
            match = re.search(r"^\s*(\d+):\s+([\w\.-]+|\?)\s+(.*)", line)
            if match:
                hop_num = match.group(1)
                hop_host = match.group(2)
                hop_info = match.group(3)
                time_match = re.search(r"([\d.]+)ms", hop_info)
                time_val = time_match.group(1) + " ms" if time_match else "N/A"
                hops.append(
                    {
                        "hop": hop_num,
                        "host": hop_host,
                        "avg_time": time_val,
                        "raw_times": hop_info,
                    }
                )
    last_results["traceroute_test"] = {
        "target": target,
        "max_hops": max_hops,
        "hops": hops,
    }
    if config["autosave_results"]:
        save_results("traceroute_test", last_results["traceroute_test"])
    add_to_history("traceroute_test", {"target": target, "max_hops": max_hops})
    prompt_enter()


# ------------------------------------------------------------------------------
# MAIN MENU FUNCTIONS
# ------------------------------------------------------------------------------
def basic_menu():
    """
    Display the basic network information menu.
    """
    while True:
        print_header()
        logging.info("Basic Network Information Menu")
        console.print(f"{NORD10}[1]{NC} Show Network Interfaces")
        console.print(f"{NORD10}[2]{NC} Show Routing Table")
        console.print(f"{NORD10}[3]{NC} Show ARP Table")
        console.print(f"{NORD10}[4]{NC} Show Network Statistics")
        console.print(f"{NORD10}[5]{NC} Show Listening Ports")
        console.print(f"{NORD10}[6]{NC} Subnet Calculator")
        console.print(f"{NORD10}[0]{NC} Return to Main Menu")
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
    Display the connectivity tests menu.
    """
    while True:
        print_header()
        logging.info("Connectivity Tests Menu")
        console.print(f"{NORD10}[1]{NC} Ping Test")
        console.print(f"{NORD10}[2]{NC} Traceroute Test")
        console.print(f"{NORD10}[3]{NC} DNS Lookup (Not Implemented)")
        console.print(f"{NORD10}[4]{NC} SSL Certificate Check (Not Implemented)")
        console.print(f"{NORD10}[5]{NC} HTTP Header Analysis (Not Implemented)")
        console.print(f"{NORD10}[0]{NC} Return to Main Menu")
        opt = input(f"{NORD8}Enter your choice: {NC}").strip()
        if opt == "1":
            ping_test()
        elif opt == "2":
            traceroute_test()
        elif opt == "3":
            console.print(f"{NORD14}DNS Lookup not implemented in this version.{NC}")
            prompt_enter()
        elif opt == "4":
            console.print(
                f"{NORD14}SSL Certificate Check not implemented in this version.{NC}"
            )
            prompt_enter()
        elif opt == "5":
            console.print(
                f"{NORD14}HTTP Header Analysis not implemented in this version.{NC}"
            )
            prompt_enter()
        elif opt == "0":
            break
        else:
            logging.warning("Invalid selection.")
            time.sleep(1)


def main_menu():
    """
    Display the main menu and handle user selections.
    """
    while True:
        print_header()
        logging.info("Main Menu")
        console.print(f"{NORD10}[1]{NC} Basic Network Information")
        console.print(f"{NORD10}[2]{NC} Connectivity Tests")
        console.print(
            f"{NORD10}[3]{NC} Port Scanning & Network Discovery (Not Implemented)"
        )
        console.print(f"{NORD10}[4]{NC} Performance Tests (Not Implemented)")
        console.print(
            f"{NORD10}[5]{NC} Advanced / Penetration Testing Tools (Not Implemented)"
        )
        console.print(f"{NORD10}[6]{NC} Extra Tools (Not Implemented)")
        console.print(f"{NORD10}[7]{NC} Settings (Not Implemented)")
        console.print(f"{NORD10}[q]{NC} Quit")
        choice = input(f"{NORD8}Enter your choice: {NC}").strip().lower()
        if choice == "1":
            basic_menu()
        elif choice == "2":
            connectivity_menu()
        elif choice == "3":
            console.print(
                f"{NORD14}Port Scanning & Network Discovery not implemented in this version.{NC}"
            )
            prompt_enter()
        elif choice == "4":
            console.print(
                f"{NORD14}Performance Tests not implemented in this version.{NC}"
            )
            prompt_enter()
        elif choice == "5":
            console.print(
                f"{NORD14}Advanced / Penetration Testing Tools not implemented in this version.{NC}"
            )
            prompt_enter()
        elif choice == "6":
            console.print(f"{NORD14}Extra Tools not implemented in this version.{NC}")
            prompt_enter()
        elif choice == "7":
            console.print(f"{NORD14}Settings not implemented in this version.{NC}")
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
    Main entry point for the enhanced network toolkit.
    """
    setup_logging()
    check_dependencies()
    check_root()
    init_config_dir()
    load_config()
    load_history()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"ENHANCED NETWORK TOOLKIT STARTED AT {now}")
    logging.info("=" * 80)
    try:
        main_menu()
    except KeyboardInterrupt:
        logging.info("Program interrupted by user.")
    except Exception as e:
        logging.error(f"Unhandled exception: {e}")
        sys.exit(1)
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
