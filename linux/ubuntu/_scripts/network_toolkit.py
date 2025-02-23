#!/usr/bin/env python3
"""
Advanced Network Toolkit
------------------------
An advanced, production‑grade network toolkit that performs common and advanced
network tests, diagnostics, performance measurements, and penetration testing tasks on Debian.
This interactive tool provides a Nord‑themed user interface with strict error handling,
detailed logging with log‑level filtering, and graceful signal traps.

Author: Your Name | License: MIT | Version: 2.0
Usage:
    sudo ./advanced_network_toolkit.py

Notes:
    - This script requires root privileges for some tests.
    - Logs are stored at /var/log/advanced_network_toolkit.log by default.
"""

import os
import sys
import shutil
import subprocess
import signal
import atexit
import time
from datetime import datetime

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES & CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE = "/var/log/advanced_network_toolkit.log"  # Log file path
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
DEFAULT_LOG_LEVEL = "INFO"

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD9  = '\033[38;2;129;161;193m'   # Bluish (DEBUG)
NORD10 = '\033[38;2;94;129;172m'    # Accent Blue (Section Headers)
NORD11 = '\033[38;2;191;97;106m'    # Reddish (ERROR/CRITICAL)
NORD13 = '\033[38;2;235;203;139m'   # Yellowish (WARN)
NORD14 = '\033[38;2;163;190;140m'   # Greenish (INFO)
NC     = '\033[0m'                 # Reset / No Color

# ------------------------------------------------------------------------------
# LOG LEVEL CONVERSION
# ------------------------------------------------------------------------------
LOG_LEVELS = {
    "VERBOSE": 0, "V": 0,
    "DEBUG": 1, "D": 1,
    "INFO": 2, "I": 2,
    "WARN": 3, "WARNING": 3, "W": 3,
    "ERROR": 4, "E": 4,
    "CRITICAL": 5, "C": 5,
}

def get_log_level_num(level: str) -> int:
    return LOG_LEVELS.get(level.upper(), 2)  # default to INFO

# ------------------------------------------------------------------------------
# LOGGING FUNCTION
# ------------------------------------------------------------------------------
def log(level: str, message: str):
    upper_level = level.upper()
    msg_level = get_log_level_num(upper_level)
    current_level = get_log_level_num(os.environ.get("LOG_LEVEL", DEFAULT_LOG_LEVEL))
    if msg_level < current_level:
        return

    # Determine color based on level
    color = NC
    if not DISABLE_COLORS:
        if upper_level == "DEBUG":
            color = NORD9
        elif upper_level == "INFO":
            color = NORD14
        elif upper_level in ("WARN", "WARNING"):
            color = NORD13
        elif upper_level in ("ERROR", "CRITICAL"):
            color = NORD11

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] [{upper_level}] {message}"

    # Append log entry to file
    try:
        with open(LOG_FILE, "a") as f:
            f.write(log_entry + "\n")
    except Exception as e:
        sys.stderr.write(f"Failed to write log: {e}\n")

    # Print to stderr with colors
    sys.stderr.write(f"{color}{log_entry}{NC}\n")

# ------------------------------------------------------------------------------
# ERROR HANDLING & CLEANUP FUNCTIONS
# ------------------------------------------------------------------------------
def handle_error(error_message="An unknown error occurred", exit_code=1, lineno=None, func="main"):
    lineno = lineno if lineno is not None else sys._getframe().f_lineno
    log("ERROR", f"{error_message} (Exit Code: {exit_code})")
    log("ERROR", f"Error in function '{func}' at line {lineno}.")
    sys.stderr.write(f"{NORD11}ERROR: {error_message} (Exit Code: {exit_code}){NC}\n")
    sys.exit(exit_code)

def cleanup():
    log("INFO", "Performing cleanup tasks before exit.")
    # Add any cleanup tasks here (e.g., remove temporary files)

atexit.register(cleanup)

def signal_handler(signum, frame):
    if signum == signal.SIGINT:
        handle_error("Script interrupted by user.", 130, func="signal_handler")
    elif signum == signal.SIGTERM:
        handle_error("Script terminated.", 143, func="signal_handler")

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------
def check_root():
    if os.getuid() != 0:
        handle_error("This script must be run as root.")

def print_section(title: str):
    border = "─" * 60
    log("INFO", f"{NORD10}{border}{NC}")
    log("INFO", f"{NORD10}  {title}{NC}")
    log("INFO", f"{NORD10}{border}{NC}")

def prompt_enter():
    input("Press Enter to continue...")

def print_header():
    os.system("clear")
    print_section("ADVANCED NETWORK TOOLKIT MENU")

def run_command(command: list, color=NORD14, timeout=None):
    """Runs a command and returns its output (or prints a warning if it fails)."""
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        output = result.stdout.strip()
        if output:
            print(f"{color}{output}{NC}")
    except Exception as e:
        log("ERROR", f"Command {' '.join(command)} failed: {e}")

def is_installed(cmd: str) -> bool:
    return shutil.which(cmd) is not None

# ------------------------------------------------------------------------------
# BASIC NETWORK INFORMATION FUNCTIONS
# ------------------------------------------------------------------------------
def show_network_interfaces():
    print_section("Network Interfaces")
    log("INFO", "Displaying network interfaces...")
    run_command(["ip", "addr", "show"])
    prompt_enter()

def show_routing_table():
    print_section("Routing Table")
    log("INFO", "Displaying routing table...")
    run_command(["ip", "route"])
    prompt_enter()

def show_arp_table():
    print_section("ARP Table")
    log("INFO", "Displaying ARP table...")
    run_command(["arp", "-a"])
    prompt_enter()

# ------------------------------------------------------------------------------
# CONNECTIVITY TEST FUNCTIONS
# ------------------------------------------------------------------------------
def ping_test():
    print_section("Ping Test")
    target = input("Enter target hostname or IP for ping test: ").strip()
    count = input("Enter count (default 5): ").strip() or "5"
    log("INFO", f"Pinging {target} for {count} packets...")
    run_command(["ping", "-c", count, target])
    prompt_enter()

def traceroute_test():
    print_section("Traceroute Test")
    target = input("Enter target hostname or IP for traceroute: ").strip()
    log("INFO", f"Performing traceroute to {target}...")
    if is_installed("traceroute"):
        run_command(["traceroute", target])
    elif is_installed("tracepath"):
        run_command(["tracepath", target])
    else:
        log("WARN", "Neither traceroute nor tracepath is installed.")
        print(f"{NORD13}Warning: Neither traceroute nor tracepath is installed.{NC}")
    prompt_enter()

def dns_lookup():
    print_section("DNS Lookup")
    domain = input("Enter domain for DNS lookup: ").strip()
    log("INFO", f"Performing DNS lookup for {domain}...")
    if is_installed("dig"):
        run_command(["dig", domain, "+short"])
    else:
        run_command(["nslookup", domain])
    prompt_enter()

# ------------------------------------------------------------------------------
# PORT SCANNING & NETWORK DISCOVERY FUNCTIONS
# ------------------------------------------------------------------------------
def port_scan():
    print_section("Port Scan")
    target = input("Enter target IP/hostname for port scan: ").strip()
    port_range = input("Enter port range (e.g., 1-1024): ").strip()
    log("INFO", f"Scanning {target} for ports in range {port_range}...")
    if is_installed("nmap"):
        run_command(["nmap", "-p", port_range, target])
    else:
        log("WARN", "nmap is not installed. Please install nmap for port scanning.")
        print(f"{NORD13}Warning: nmap is not installed.{NC}")
    prompt_enter()

def local_network_scan():
    print_section("Local Network Scan")
    subnet = input("Enter local subnet (e.g., 192.168.1.0/24): ").strip()
    log("INFO", f"Scanning local network on subnet {subnet}...")
    if is_installed("nmap"):
        run_command(["nmap", "-sn", subnet])
    else:
        log("WARN", "nmap is not installed. Please install nmap for network discovery.")
        print(f"{NORD13}Warning: nmap is not installed.{NC}")
    prompt_enter()

# ------------------------------------------------------------------------------
# PERFORMANCE TEST FUNCTIONS
# ------------------------------------------------------------------------------
def speed_test():
    print_section("Speed Test")
    log("INFO", "Running WAN speed test...")
    if is_installed("speedtest-cli"):
        run_command(["speedtest-cli"])
    else:
        log("WARN", "speedtest-cli is not installed. Please install it for WAN performance tests.")
        print(f"{NORD13}Warning: speedtest-cli is not installed.{NC}")
    prompt_enter()

def iperf_test():
    print_section("Iperf Test")
    server = input("Enter iperf server address: ").strip()
    log("INFO", f"Running iperf test against {server}...")
    if is_installed("iperf3"):
        run_command(["iperf3", "-c", server])
    elif is_installed("iperf"):
        run_command(["iperf", "-c", server])
    else:
        log("WARN", "iperf is not installed. Please install iperf3 for performance tests.")
        print(f"{NORD13}Warning: iperf is not installed.{NC}")
    prompt_enter()

# ------------------------------------------------------------------------------
# ADVANCED / PENETRATION TESTING FUNCTIONS
# ------------------------------------------------------------------------------
def syn_scan():
    print_section("SYN Scan")
    target = input("Enter target IP/hostname for SYN scan (requires hping3): ").strip()
    port = input("Enter target port (default 80): ").strip() or "80"
    log("INFO", f"Performing SYN scan on {target}:{port}...")
    if is_installed("hping3"):
        run_command(["hping3", "-S", "-p", port, target, "-c", "5"])
    else:
        log("WARN", "hping3 is not installed. Please install hping3 for SYN scanning.")
        print(f"{NORD13}Warning: hping3 is not installed.{NC}")
    prompt_enter()

def banner_grab():
    print_section("Banner Grab")
    target = input("Enter target IP/hostname for banner grab: ").strip()
    port = input("Enter target port (default 80): ").strip() or "80"
    log("INFO", f"Grabbing banner from {target}:{port}...")
    if is_installed("nc"):
        # Using timeout for safety; note that 'timeout' should be available on your system.
        run_command(["timeout", "5", "nc", target, port])
    else:
        log("WARN", "netcat (nc) is not installed. Please install it for banner grabbing.")
        print(f"{NORD13}Warning: netcat (nc) is not installed.{NC}")
    prompt_enter()

# ------------------------------------------------------------------------------
# FIREWALL & WIFI TOOLS FUNCTIONS
# ------------------------------------------------------------------------------
def firewall_check():
    print_section("Firewall Status")
    log("INFO", "Checking firewall status...")
    if is_installed("ufw"):
        run_command(["ufw", "status", "verbose"])
    elif is_installed("iptables"):
        run_command(["iptables", "-L", "-n"])
    else:
        log("WARN", "No firewall tool detected.")
        print(f"{NORD13}Warning: No firewall tool detected.{NC}")
    prompt_enter()

def wifi_scan():
    print_section("WiFi Scan")
    log("INFO", "Scanning for WiFi networks...")
    if is_installed("nmcli"):
        run_command(["nmcli", "device", "wifi", "list"])
    else:
        log("WARN", "nmcli is not installed. Please install NetworkManager CLI for WiFi scanning.")
        print(f"{NORD13}Warning: nmcli is not installed.{NC}")
    prompt_enter()

# ------------------------------------------------------------------------------
# MENU FUNCTIONS
# ------------------------------------------------------------------------------
def basic_menu():
    while True:
        print_header()
        log("INFO", "Basic Network Information:")
        print(f"{NORD10}[1]{NC} Show Network Interfaces")
        print(f"{NORD10}[2]{NC} Show Routing Table")
        print(f"{NORD10}[3]{NC} Show ARP Table")
        print(f"{NORD10}[0]{NC} Return to Main Menu")
        opt = input("Enter your choice: ").strip()
        if opt == "1":
            show_network_interfaces()
        elif opt == "2":
            show_routing_table()
        elif opt == "3":
            show_arp_table()
        elif opt == "0":
            break
        else:
            log("WARN", "Invalid selection.")
            time.sleep(1)

def connectivity_menu():
    while True:
        print_header()
        log("INFO", "Connectivity Tests:")
        print(f"{NORD10}[1]{NC} Ping Test")
        print(f"{NORD10}[2]{NC} Traceroute Test")
        print(f"{NORD10}[3]{NC} DNS Lookup")
        print(f"{NORD10}[0]{NC} Return to Main Menu")
        opt = input("Enter your choice: ").strip()
        if opt == "1":
            ping_test()
        elif opt == "2":
            traceroute_test()
        elif opt == "3":
            dns_lookup()
        elif opt == "0":
            break
        else:
            log("WARN", "Invalid selection.")
            time.sleep(1)

def scanning_menu():
    while True:
        print_header()
        log("INFO", "Port Scanning & Network Discovery:")
        print(f"{NORD10}[1]{NC} Port Scan")
        print(f"{NORD10}[2]{NC} Local Network Scan")
        print(f"{NORD10}[0]{NC} Return to Main Menu")
        opt = input("Enter your choice: ").strip()
        if opt == "1":
            port_scan()
        elif opt == "2":
            local_network_scan()
        elif opt == "0":
            break
        else:
            log("WARN", "Invalid selection.")
            time.sleep(1)

def performance_menu():
    while True:
        print_header()
        log("INFO", "Performance Tests:")
        print(f"{NORD10}[1]{NC} Speed Test (WAN)")
        print(f"{NORD10}[2]{NC} Iperf Test")
        print(f"{NORD10}[0]{NC} Return to Main Menu")
        opt = input("Enter your choice: ").strip()
        if opt == "1":
            speed_test()
        elif opt == "2":
            iperf_test()
        elif opt == "0":
            break
        else:
            log("WARN", "Invalid selection.")
            time.sleep(1)

def advanced_menu():
    while True:
        print_header()
        log("INFO", "Advanced / Penetration Testing Tools:")
        print(f"{NORD10}[1]{NC} SYN Scan (hping3)")
        print(f"{NORD10}[2]{NC} Banner Grabbing (netcat)")
        print(f"{NORD10}[0]{NC} Return to Main Menu")
        opt = input("Enter your choice: ").strip()
        if opt == "1":
            syn_scan()
        elif opt == "2":
            banner_grab()
        elif opt == "0":
            break
        else:
            log("WARN", "Invalid selection.")
            time.sleep(1)

def extras_menu():
    while True:
        print_header()
        log("INFO", "Firewall & WiFi Tools:")
        print(f"{NORD10}[1]{NC} Check Firewall Status")
        print(f"{NORD10}[2]{NC} Scan WiFi Networks")
        print(f"{NORD10}[0]{NC} Return to Main Menu")
        opt = input("Enter your choice: ").strip()
        if opt == "1":
            firewall_check()
        elif opt == "2":
            wifi_scan()
        elif opt == "0":
            break
        else:
            log("WARN", "Invalid selection.")
            time.sleep(1)

def main_menu():
    while True:
        print_header()
        log("INFO", "Select an option:")
        print(f"{NORD10}[1]{NC} Basic Network Information")
        print(f"{NORD10}[2]{NC} Connectivity Tests")
        print(f"{NORD10}[3]{NC} Port Scanning & Network Discovery")
        print(f"{NORD10}[4]{NC} Performance Tests")
        print(f"{NORD10}[5]{NC} Advanced / Penetration Testing Tools")
        print(f"{NORD10}[6]{NC} Firewall & WiFi Tools")
        print(f"{NORD10}[q]{NC} Quit")
        choice = input("Enter your choice: ").strip().lower()
        if choice == "1":
            basic_menu()
        elif choice == "2":
            connectivity_menu()
        elif choice == "3":
            scanning_menu()
        elif choice == "4":
            performance_menu()
        elif choice == "5":
            advanced_menu()
        elif choice == "6":
            extras_menu()
        elif choice == "q":
            log("INFO", "Exiting. Goodbye!")
            sys.exit(0)
        else:
            log("WARN", "Invalid selection. Please choose a valid option.")
            time.sleep(1)

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
def main():
    if not sys.argv[0].endswith(".py"):
        # If somehow not executed as a Python script.
        handle_error("Please run this script with Python.", func="main")
    check_root()

    # Ensure log directory exists and file is created with secure permissions.
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        try:
            os.makedirs(log_dir, exist_ok=True)
        except Exception as e:
            handle_error(f"Failed to create log directory: {log_dir} ({e})")
    try:
        with open(LOG_FILE, "a") as f:
            pass
    except Exception as e:
        handle_error(f"Failed to create log file: {LOG_FILE} ({e})")
    try:
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        handle_error(f"Failed to set permissions on {LOG_FILE} ({e})")

    log("INFO", "Advanced Network Toolkit execution started.")

    # Loop the main menu
    while True:
        main_menu()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        handle_error(f"Unhandled exception: {e}", exit_code=1, func="main")