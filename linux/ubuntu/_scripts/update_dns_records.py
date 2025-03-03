#!/usr/bin/env python3
"""
Enhanced DNS Records Updater
--------------------------------------------------

A streamlined terminal interface for updating Cloudflare DNS A records
with your current public IP address. Features Nord theme styling,
comprehensive logging, error handling, and graceful signal management.

Usage:
  sudo ./dns_updater.py
  - Option 1: Update DNS Records
  - Option 2: View Current Public IP
  - Option 3: View Configuration
  - Option 4: Exit

  For non-interactive use:
  sudo ./dns_updater.py --non-interactive

Requirements:
  - Root privileges
  - Environment variables CF_API_TOKEN and CF_ZONE_ID (set in /etc/environment)
  - Python libraries: rich, pyfiglet

Version: 5.0.0
"""

import atexit
import json
import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen
from typing import Any, Dict, List, Optional, Callable, Tuple

# ----------------------------------------------------------------
# Dependency Check and Imports
# ----------------------------------------------------------------
try:
    import pyfiglet
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TimeRemainingColumn,
    )
    from rich.align import Align
    from rich.style import Style
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print("This script requires the 'rich' and 'pyfiglet' libraries.")
    print("Please install them using: pip install rich pyfiglet")
    sys.exit(1)

# Install rich traceback handler for better error reporting
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------
VERSION: str = "5.0.0"
APP_NAME: str = "DNS Updater"
APP_SUBTITLE: str = "Cloudflare DNS Manager"

# Log file location
LOG_FILE: str = "/var/log/dns_updater.log"
DEFAULT_LOG_LEVEL: str = "INFO"

# Terminal display settings
TERM_WIDTH: int = 80  # Adjust based on terminal size

# Operation timeouts
REQUEST_TIMEOUT: float = 10.0  # seconds
OPERATION_TIMEOUT: int = 30  # seconds

# Cloudflare API credentials (must be set in the environment)
CF_API_TOKEN: Optional[str] = os.environ.get("CF_API_TOKEN")
CF_ZONE_ID: Optional[str] = os.environ.get("CF_ZONE_ID")

# Fallback services for retrieving public IP
IP_SERVICES: List[str] = [
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
    "https://checkip.amazonaws.com",
]


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming throughout the application."""

    # Polar Night (dark) shades
    POLAR_NIGHT_1 = "#2E3440"  # Darkest background shade
    POLAR_NIGHT_4 = "#4C566A"  # Light background shade

    # Snow Storm (light) shades
    SNOW_STORM_1 = "#D8DEE9"  # Darkest text color
    SNOW_STORM_2 = "#E5E9F0"  # Medium text color

    # Frost (blues/cyans) shades
    FROST_1 = "#8FBCBB"  # Light cyan
    FROST_2 = "#88C0D0"  # Light blue
    FROST_3 = "#81A1C1"  # Medium blue
    FROST_4 = "#5E81AC"  # Dark blue

    # Aurora (accent) shades
    RED = "#BF616A"  # Red
    ORANGE = "#D08770"  # Orange
    YELLOW = "#EBCB8B"  # Yellow
    GREEN = "#A3BE8C"  # Green


# Create a Rich Console
console: Console = Console(theme=None, highlight=False)


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
class DNSRecord:
    """
    Represents a DNS record with its details and status.

    Attributes:
        id: The unique identifier of the DNS record
        name: The domain name (e.g., example.com)
        type: The record type (e.g., A, CNAME)
        content: The current IP address or target
        proxied: Whether the record is proxied through Cloudflare
        updated: Whether the record has been updated in the current session
    """

    def __init__(
        self, id: str, name: str, type: str, content: str, proxied: bool = False
    ) -> None:
        self.id: str = id
        self.name: str = name
        self.type: str = type
        self.content: str = content
        self.proxied: bool = proxied
        self.updated: bool = False

    def __str__(self) -> str:
        return f"{self.name} ({self.type}): {self.content}"


# ----------------------------------------------------------------
# Console and Logging Helpers
# ----------------------------------------------------------------
def create_header() -> Panel:
    """
    Create a high-tech ASCII art header with impressive styling.

    Returns:
        Panel containing the styled header
    """
    # Use smaller, more compact but still tech-looking fonts
    compact_fonts = ["slant", "small", "smslant", "digital", "standard"]

    # Try each font until we find one that works well
    for font_name in compact_fonts:
        try:
            fig = pyfiglet.Figlet(font=font_name, width=60)  # Constrained width
            ascii_art = fig.renderText(APP_NAME)

            # If we got a reasonable result, use it
            if ascii_art and len(ascii_art.strip()) > 0:
                break
        except Exception:
            continue

    # Custom ASCII art fallback if all else fails
    if not ascii_art or len(ascii_art.strip()) == 0:
        ascii_art = """
     _                             _       _            
  __| |_ __  ___   _   _ _ __   __| | __ _| |_ ___ _ __ 
 / _` | '_ \/ __| | | | | '_ \ / _` |/ _` | __/ _ \ '__|
| (_| | | | \__ \ | |_| | |_) | (_| | (_| | ||  __/ |   
 \__,_|_| |_|___/  \__,_| .__/ \__,_|\__,_|\__\___|_|   
                        |_|                             
        """

    # Clean up extra whitespace that might cause display issues
    ascii_lines = [line for line in ascii_art.split("\n") if line.strip()]

    # Create a high-tech gradient effect with Nord colors
    colors = [
        NordColors.FROST_1,
        NordColors.FROST_2,
        NordColors.FROST_3,
        NordColors.FROST_2,
    ]

    styled_text = ""
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        styled_text += f"[bold {color}]{line}[/]\n"

    # Add decorative tech elements
    tech_border = f"[{NordColors.FROST_3}]" + "━" * 30 + "[/]"
    styled_text = tech_border + "\n" + styled_text + tech_border

    # Create a panel with sufficient padding to avoid cutoff
    header_panel = Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 1),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )

    return header_panel


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    """
    Print a styled message.

    Args:
        text: The message to display
        style: The color style to use
        prefix: The prefix symbol
    """
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def display_panel(
    message: str, style: str = NordColors.FROST_2, title: Optional[str] = None
) -> None:
    """
    Display a message in a styled panel.

    Args:
        message: The message to display
        style: The color style to use
        title: Optional panel title
    """
    panel = Panel(
        Text.from_markup(f"[bold {style}]{message}[/]"),
        border_style=Style(color=style),
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


def setup_logging() -> None:
    """Set up logging to both console and file."""
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Remove any existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    try:
        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        print_message(
            f"Failed to set up log file {LOG_FILE}: {e}", NordColors.YELLOW, "⚠"
        )
        print_message("Continuing with console logging only", NordColors.YELLOW, "⚠")


# ----------------------------------------------------------------
# Command Execution Helper
# ----------------------------------------------------------------
def run_command(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = True,
    timeout: int = OPERATION_TIMEOUT,
) -> subprocess.CompletedProcess:
    """
    Executes a system command and returns the CompletedProcess.

    Args:
        cmd: Command and arguments as a list
        env: Environment variables for the command
        check: Whether to check the return code
        capture_output: Whether to capture stdout/stderr
        timeout: Command timeout in seconds

    Returns:
        CompletedProcess instance with command results
    """
    try:
        import subprocess

        result = subprocess.run(
            cmd,
            env=env or os.environ.copy(),
            check=check,
            text=True,
            capture_output=capture_output,
            timeout=timeout,
        )
        return result
    except subprocess.CalledProcessError as e:
        print_message(f"Command failed: {' '.join(cmd)}", NordColors.RED, "✗")
        if e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if e.stderr:
            console.print(f"[bold {NordColors.RED}]Stderr: {e.stderr.strip()}[/]")
        raise
    except subprocess.TimeoutExpired:
        print_message(f"Command timed out after {timeout} seconds", NordColors.RED, "✗")
        raise
    except Exception as e:
        print_message(f"Error executing command: {e}", NordColors.RED, "✗")
        raise


# ----------------------------------------------------------------
# Progress Display Class
# ----------------------------------------------------------------
class ConsoleSpinner:
    """A spinner to indicate progress for operations with unknown duration."""

    def __init__(self, message: str) -> None:
        self.message = message
        self.spinning = True
        self.spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self.current = 0
        self.start_time = time.time()
        self.thread = threading.Thread(target=self._spin, daemon=True)

    def _spin(self) -> None:
        while self.spinning:
            elapsed = time.time() - self.start_time
            sys.stdout.write(
                f"\r{self.spinner_chars[self.current]} {self.message} [{elapsed:.1f}s elapsed]"
            )
            sys.stdout.flush()
            self.current = (self.current + 1) % len(self.spinner_chars)
            time.sleep(0.1)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.spinning = False
        self.thread.join()
        sys.stdout.write("\r" + " " * TERM_WIDTH + "\r")
        sys.stdout.flush()


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    """Perform cleanup tasks before exit."""
    print_message("Performing cleanup tasks before exit.", NordColors.FROST_3)
    logging.info("Performing cleanup tasks before exit.")


def signal_handler(sig: int, frame: Any) -> None:
    """
    Handle process termination signals gracefully.

    Args:
        sig: Signal number
        frame: Current stack frame
    """
    sig_name: str = (
        signal.Signals(sig).name if hasattr(signal, "Signals") else f"signal {sig}"
    )
    print_message(f"Process interrupted by {sig_name}", NordColors.YELLOW, "⚠")
    logging.error(f"Script interrupted by {sig_name}.")
    cleanup()
    sys.exit(128 + sig)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Validation and Prerequisite Checks
# ----------------------------------------------------------------
def check_dependencies() -> None:
    """Ensure required Python packages are installed."""
    try:
        import rich
        import pyfiglet
    except ImportError as e:
        print_message(f"Missing required dependency: {e}", NordColors.RED, "✗")
        print("Please install required packages using pip: pip install rich pyfiglet")
        sys.exit(1)


def check_root() -> None:
    """Ensure the script is run as root."""
    if os.geteuid() != 0:
        print_message("This script must be run as root.", NordColors.RED, "✗")
        sys.exit(1)


def validate_config() -> None:
    """Ensure required environment variables are set."""
    if not CF_API_TOKEN:
        print_message(
            "Environment variable 'CF_API_TOKEN' is not set. Please set it in /etc/environment.",
            NordColors.RED,
            "✗",
        )
        sys.exit(1)
    if not CF_ZONE_ID:
        print_message(
            "Environment variable 'CF_ZONE_ID' is not set. Please set it in /etc/environment.",
            NordColors.RED,
            "✗",
        )
        sys.exit(1)


# ----------------------------------------------------------------
# Network Functions
# ----------------------------------------------------------------
def get_public_ip() -> str:
    """
    Retrieve the current public IP address using fallback services.

    Returns:
        The current public IP address as a string
    """
    for service_url in IP_SERVICES:
        try:
            print_message(
                f"Retrieving public IP from {service_url}", NordColors.FROST_2, "→"
            )
            logging.debug(f"Retrieving public IP from {service_url}")
            req = Request(service_url)
            with urlopen(req, timeout=REQUEST_TIMEOUT) as response:
                ip = response.read().decode().strip()
                if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip):
                    print_message(
                        f"Public IP from {service_url}: {ip}", NordColors.GREEN, "✓"
                    )
                    logging.info(f"Public IP from {service_url}: {ip}")
                    return ip
                else:
                    print_message(
                        f"Invalid IP format from {service_url}: {ip}",
                        NordColors.YELLOW,
                        "⚠",
                    )
                    logging.warning(f"Invalid IP format from {service_url}: {ip}")
        except Exception as e:
            print_message(
                f"Failed to get public IP from {service_url}: {e}",
                NordColors.YELLOW,
                "⚠",
            )
            logging.warning(f"Failed to get public IP from {service_url}: {e}")

    print_message(
        "Failed to retrieve public IP from all services.", NordColors.RED, "✗"
    )
    logging.error("Failed to retrieve public IP from all services.")
    sys.exit(1)


# ----------------------------------------------------------------
# Cloudflare API Functions
# ----------------------------------------------------------------
def fetch_dns_records() -> List[DNSRecord]:
    """
    Fetch all DNS A records from Cloudflare.

    Returns:
        List of DNSRecord objects
    """
    url = f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE_ID}/dns_records?type=A"
    headers = {
        "Authorization": f"Bearer {CF_API_TOKEN}",
        "Content-Type": "application/json",
    }
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=REQUEST_TIMEOUT) as response:
            data = json.loads(response.read().decode())
            if "result" not in data:
                print_message(
                    "Unexpected response format from Cloudflare API.",
                    NordColors.RED,
                    "✗",
                )
                logging.error("Unexpected response format from Cloudflare API.")
                sys.exit(1)

            records = []
            for record_data in data["result"]:
                if record_data.get("type") == "A":
                    record = DNSRecord(
                        id=record_data.get("id"),
                        name=record_data.get("name"),
                        type=record_data.get("type"),
                        content=record_data.get("content"),
                        proxied=record_data.get("proxied", False),
                    )
                    records.append(record)

            return records
    except Exception as e:
        print_message(
            f"Failed to fetch DNS records from Cloudflare: {e}", NordColors.RED, "✗"
        )
        logging.error(f"Failed to fetch DNS records from Cloudflare: {e}")
        sys.exit(1)


def update_dns_record(record: DNSRecord, new_ip: str) -> bool:
    """
    Update a single DNS A record with the new IP address.

    Args:
        record: The DNSRecord object to update
        new_ip: The new IP address

    Returns:
        True if update was successful, False otherwise
    """
    url = f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE_ID}/dns_records/{record.id}"
    headers = {
        "Authorization": f"Bearer {CF_API_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "type": "A",
        "name": record.name,
        "content": new_ip,
        "ttl": 1,
        "proxied": record.proxied,
    }
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers=headers, method="PUT")
    try:
        with urlopen(req, timeout=REQUEST_TIMEOUT) as response:
            result = json.loads(response.read().decode())
            if not result.get("success"):
                errors = ", ".join(
                    error.get("message", "Unknown error")
                    for error in result.get("errors", [])
                )
                print_message(
                    f"Failed to update record '{record.name}': {errors}",
                    NordColors.YELLOW,
                    "⚠",
                )
                logging.warning(f"Failed to update record '{record.name}': {errors}")
                return False

            print_message(
                f"Successfully updated DNS record '{record.name}'",
                NordColors.GREEN,
                "✓",
            )
            logging.info(f"Successfully updated DNS record '{record.name}'")
            record.content = new_ip
            record.updated = True
            return True
    except Exception as e:
        print_message(
            f"Error updating DNS record '{record.name}': {e}", NordColors.YELLOW, "⚠"
        )
        logging.warning(f"Error updating DNS record '{record.name}': {e}")
        return False


# ----------------------------------------------------------------
# UI Components
# ----------------------------------------------------------------
def create_records_table(records: List[DNSRecord], title: str) -> Table:
    """
    Create a table displaying DNS record information.

    Args:
        records: List of DNSRecord objects to display
        title: Title for the records table

    Returns:
        A Rich Table object containing the DNS records information
    """
    table = Table(
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        expand=True,
        title=f"[bold {NordColors.FROST_2}]{title}[/]",
        border_style=NordColors.FROST_3,
        title_justify="center",
    )

    table.add_column("Name", style=f"bold {NordColors.FROST_1}")
    table.add_column("Type", style=f"{NordColors.FROST_3}", justify="center", width=8)
    table.add_column("IP Address", style=f"{NordColors.SNOW_STORM_1}")
    table.add_column(
        "Proxied", style=f"{NordColors.FROST_4}", justify="center", width=10
    )
    table.add_column("Status", justify="center", width=12)

    for record in records:
        # Create status indicator
        if record.updated:
            status = Text("● UPDATED", style=f"bold {NordColors.GREEN}")
        else:
            status = Text("● UNCHANGED", style=f"dim {NordColors.POLAR_NIGHT_4}")

        proxied_text = "Yes" if record.proxied else "No"

        table.add_row(record.name, record.type, record.content, proxied_text, status)

    return table


# ----------------------------------------------------------------
# Main Functionality
# ----------------------------------------------------------------
def update_cloudflare_dns() -> Tuple[int, int]:
    """
    Update Cloudflare DNS A records with the current public IP address.

    Returns:
        A tuple containing (number of updates, number of errors)
    """
    panel_title = "Cloudflare DNS Update Process"
    display_panel(
        "Starting DNS update process. This will update all A records to your current public IP.",
        style=NordColors.FROST_3,
        title=panel_title,
    )
    logging.info("Starting Cloudflare DNS update process")

    # Get current public IP
    print_message("Fetching current public IP...", NordColors.FROST_3)
    logging.info("Fetching current public IP...")
    with ConsoleSpinner("Retrieving public IP..."):
        current_ip = get_public_ip()
    print_message(f"Current public IP: {current_ip}", NordColors.FROST_2)
    logging.info(f"Current public IP: {current_ip}")

    # Fetch DNS records
    print_message("Fetching DNS records from Cloudflare...", NordColors.FROST_3)
    logging.info("Fetching DNS records from Cloudflare...")
    with ConsoleSpinner("Fetching DNS records..."):
        records = fetch_dns_records()
    print_message(f"Found {len(records)} DNS A records", NordColors.FROST_2)
    logging.info(f"Found {len(records)} DNS A records")

    # Update records if needed
    updates = 0
    errors = 0

    with Progress(
        SpinnerColumn(style=f"bold {NordColors.FROST_1}"),
        TextColumn(f"[bold {NordColors.FROST_2}]{{task.description}}"),
        BarColumn(complete_style=NordColors.GREEN, finished_style=NordColors.GREEN),
        TextColumn(f"[{NordColors.SNOW_STORM_1}]{{task.completed}}/{{task.total}}"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Updating DNS records...", total=len(records))

        for record in records:
            progress.update(task, description=f"Processing '{record.name}'")

            if record.content != current_ip:
                logging.info(
                    f"Updating '{record.name}': {record.content} → {current_ip}"
                )
                if update_dns_record(record, current_ip):
                    updates += 1
                else:
                    errors += 1
            else:
                logging.debug(
                    f"No update needed for '{record.name}' (IP: {record.content})"
                )

            progress.update(task, advance=1)

    # Display results
    if errors > 0:
        print_message(
            f"Completed with {errors} error(s) and {updates} update(s)",
            NordColors.YELLOW,
            "⚠",
        )
        logging.warning(f"Completed with {errors} error(s) and {updates} update(s)")
    elif updates > 0:
        print_message(
            f"Completed successfully with {updates} update(s)", NordColors.GREEN, "✓"
        )
        logging.info(f"Completed successfully with {updates} update(s)")
    else:
        print_message("No DNS records required updating", NordColors.GREEN, "✓")
        logging.info("No DNS records required updating")

    # Display updated records table
    if len(records) > 0:
        console.print(create_records_table(records, "DNS Records Status"))

    return updates, errors


# ----------------------------------------------------------------
# Interactive Menu Functions
# ----------------------------------------------------------------
def display_menu() -> str:
    """
    Display the main menu and get user choice.

    Returns:
        The user's choice as a string
    """
    console.print()
    console.print(f"[bold {NordColors.FROST_2}]{'Main Menu'.center(40)}[/]")
    console.print(f"[{NordColors.FROST_3}]{'=' * 40}[/]")
    console.print(f"[{NordColors.SNOW_STORM_1}]1. Update DNS Records[/]")
    console.print(f"[{NordColors.SNOW_STORM_1}]2. View Current Public IP[/]")
    console.print(f"[{NordColors.SNOW_STORM_1}]3. View Configuration[/]")
    console.print(f"[{NordColors.SNOW_STORM_1}]4. Exit[/]")
    console.print()
    console.print(f"[bold {NordColors.FROST_2}]Enter your choice (1-4):[/]", end=" ")
    return input().strip()


def interactive_menu() -> None:
    """Display an interactive menu for updating DNS records."""
    while True:
        console.clear()
        console.print(create_header())

        # Display current date/time and system info
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        hostname = os.uname().nodename
        console.print(
            Align.center(
                f"[{NordColors.SNOW_STORM_1}]Current Time: {current_time}[/] | "
                f"[{NordColors.SNOW_STORM_1}]Host: {hostname}[/]"
            )
        )

        choice = display_menu()

        if choice == "1":
            console.clear()
            console.print(create_header())

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logging.info("=" * 60)
            logging.info(f"DNS UPDATE STARTED AT {now}")
            logging.info("=" * 60)

            updates, errors = update_cloudflare_dns()

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logging.info("=" * 60)
            if errors == 0:
                logging.info(f"DNS UPDATE COMPLETED SUCCESSFULLY AT {now}")
            else:
                logging.warning(f"DNS UPDATE COMPLETED WITH ERRORS AT {now}")
            logging.info("=" * 60)

        elif choice == "2":
            console.clear()
            console.print(create_header())
            display_panel(
                "Current Public IP",
                style=NordColors.FROST_3,
                title="Network Information",
            )

            with ConsoleSpinner("Retrieving public IP..."):
                current_ip = get_public_ip()

            ip_panel = Panel(
                Text.from_markup(f"[bold {NordColors.SNOW_STORM_2}]{current_ip}[/]"),
                title=f"[bold {NordColors.FROST_2}]Your Public IP Address[/]",
                border_style=Style(color=NordColors.FROST_3),
                padding=(1, 2),
            )
            console.print(ip_panel)

        elif choice == "3":
            console.clear()
            console.print(create_header())
            display_panel(
                "Configuration Information",
                style=NordColors.FROST_3,
                title="System Configuration",
            )

            config_table = Table(
                show_header=True,
                header_style=f"bold {NordColors.FROST_1}",
                expand=True,
                border_style=NordColors.FROST_3,
            )

            config_table.add_column("Setting", style=f"bold {NordColors.FROST_2}")
            config_table.add_column("Value", style=f"{NordColors.SNOW_STORM_1}")

            config_table.add_row("Log File", LOG_FILE)
            config_table.add_row(
                "Zone ID", CF_ZONE_ID if CF_ZONE_ID else "Not configured"
            )
            config_table.add_row(
                "API Token", "Configured" if CF_API_TOKEN else "Not configured"
            )
            config_table.add_row("IP Services", ", ".join(IP_SERVICES))
            config_table.add_row("Version", VERSION)

            console.print(config_table)

        elif choice == "4":
            console.clear()
            console.print(create_header())
            display_panel(
                "Thank you for using the DNS Updater!",
                style=NordColors.FROST_2,
                title="Goodbye",
            )
            break

        else:
            print_message(
                "Invalid choice. Please enter a number between 1 and 4.",
                NordColors.RED,
                "✗",
            )

        if choice != "4":
            console.print()
            console.print(
                f"[{NordColors.SNOW_STORM_1}]Press Enter to return to the menu...[/]"
            )
            input()


# ----------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------
def main() -> None:
    """Main function: set up logging, validate configuration, and run the updater."""
    try:
        console.clear()
        console.print(create_header())

        # Display initialization message
        init_panel = Panel(
            Text.from_markup(
                f"[{NordColors.SNOW_STORM_1}]Initializing DNS Updater v{VERSION}[/]"
            ),
            border_style=Style(color=NordColors.FROST_3),
            title=f"[bold {NordColors.FROST_2}]System Initialization[/]",
            subtitle=f"[{NordColors.SNOW_STORM_1}]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/]",
            subtitle_align="right",
            padding=(1, 2),
        )
        console.print(init_panel)

        # Setup and validation
        print_message("Setting up logging...", NordColors.FROST_2, "→")
        setup_logging()

        print_message("Checking dependencies...", NordColors.FROST_2, "→")
        check_dependencies()

        print_message("Checking root privileges...", NordColors.FROST_2, "→")
        check_root()

        print_message("Validating configuration...", NordColors.FROST_2, "→")
        validate_config()

        print_message("Initialization complete!", NordColors.GREEN, "✓")
        time.sleep(1)  # Brief pause for visual effect

        # Check for non-interactive mode
        if len(sys.argv) > 1 and sys.argv[1] == "--non-interactive":
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logging.info("=" * 60)
            logging.info(f"DNS UPDATE STARTED AT {now} (NON-INTERACTIVE MODE)")
            logging.info("=" * 60)

            updates, errors = update_cloudflare_dns()

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logging.info("=" * 60)
            if errors == 0:
                logging.info(f"DNS UPDATE COMPLETED SUCCESSFULLY AT {now}")
            else:
                logging.warning(f"DNS UPDATE COMPLETED WITH ERRORS AT {now}")
            logging.info("=" * 60)
        else:
            interactive_menu()
    except KeyboardInterrupt:
        print_message("\nOperation cancelled by user", NordColors.YELLOW, "⚠")
        sys.exit(130)
    except Exception as e:
        print_message(f"Unexpected error: {e}", NordColors.RED, "✗")
        logging.exception("Unhandled exception")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
