#!/usr/bin/env python3
"""
Real-Time Hard Drive Storage Space Analyzer
---------------------------------------------
Description:
  An interactive Rich CLI application that continuously monitors all found hard drives
  on the system. The app displays each drive’s mount point, filesystem, total/used/free space,
  usage percentage, and real-time read/write byte rates. It uses the psutil library for system
  metrics and the Rich library for a visually engaging, Nord-themed interface.

Usage:
  sudo python3 real_time_storage_analyzer.py

Author: Your Name | License: MIT | Version: 1.0.0
"""

import logging
import os
import re
import signal
import sys
import time
from datetime import datetime

import psutil
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich import box

# ------------------------------------------------------------------------------
# Nord Color Palette (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0 = "\033[38;2;46;52;64m"    # Dark background
NORD1 = "\033[38;2;59;66;82m"    # Darker gray
NORD3 = "\033[38;2;76;86;106m"   # Light gray
NORD4 = "\033[38;2;216;222;233m" # Light foreground
NORD7 = "\033[38;2;143;188;187m" # Pale blue
NORD8 = "\033[38;2;136;192;208m" # Light blue
NORD9 = "\033[38;2;129;161;193m" # Blue
NORD10 = "\033[38;2;94;129;172m" # Dark blue
NORD11 = "\033[38;2;191;97;106m" # Red
NORD12 = "\033[38;2;208;135;112m" # Orange
NORD13 = "\033[38;2;235;203;139m" # Yellow
NORD14 = "\033[38;2;163;190;140m" # Green
NORD15 = "\033[38;2;180;142;173m" # Purple
NC = "\033[0m"                   # Reset

# ------------------------------------------------------------------------------
# Logging Configuration
# ------------------------------------------------------------------------------
class NordColorFormatter(logging.Formatter):
    """Custom logging formatter with Nord theme colors."""
    def __init__(self, fmt=None, datefmt=None, use_colors=True):
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors

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

def setup_logging() -> logging.Logger:
    """
    Set up logging with console output using Nord theme colors.
    Returns:
        logging.Logger: Configured logger instance
    """
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    # Remove existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    console_formatter = NordColorFormatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    return logger

logger = setup_logging()

# ------------------------------------------------------------------------------
# Signal Handling & Cleanup
# ------------------------------------------------------------------------------
def signal_handler(signum, frame) -> None:
    """
    Handle termination signals gracefully.
    """
    sig_name = getattr(signal, "Signals", signum).name if hasattr(signal, "Signals") else f"signal {signum}"
    logger.error(f"Script interrupted by {sig_name}. Exiting gracefully...")
    sys.exit(0)

for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)

# ------------------------------------------------------------------------------
# Helper Functions for Disk Analysis
# ------------------------------------------------------------------------------
def get_base_device(device: str) -> str:
    """
    Extract the base device name from a partition device string.
    Example: '/dev/sda1' -> 'sda'
    """
    base = os.path.basename(device)
    # Remove trailing digits (common for partition names)
    base = re.sub(r'\d+$', '', base)
    return base

def get_disk_data(previous_io: dict) -> (Table, dict):
    """
    Build and return a Rich Table containing disk usage and IO statistics,
    and update the previous IO dictionary.
    Args:
        previous_io (dict): Previous IO counters for calculating rates.
    Returns:
        (Table, dict): A Rich Table with disk stats and the current IO counters.
    """
    # Create table with Nord-themed header styling
    table = Table(title="Real-Time Hard Drive Storage Analyzer", box=box.ROUNDED, title_style="bold rgb(94,129,172)")
    table.add_column("Device", style="bold", justify="center")
    table.add_column("Mount", style="dim", justify="center")
    table.add_column("FS", justify="center")
    table.add_column("Total", justify="right")
    table.add_column("Used", justify="right")
    table.add_column("Free", justify="right")
    table.add_column("Usage %", justify="right")
    table.add_column("Read/s", justify="right")
    table.add_column("Write/s", justify="right")

    # Get current IO counters for each disk (per disk)
    current_io = psutil.disk_io_counters(perdisk=True)

    # Loop over all partitions
    for partition in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(partition.mountpoint)
        except Exception as e:
            logger.warning(f"Could not get usage for {partition.device}: {e}")
            continue

        base_dev = get_base_device(partition.device)
        io = current_io.get(base_dev) or current_io.get(partition.device)
        prev = previous_io.get(base_dev) or previous_io.get(partition.device)
        if io and prev:
            read_rate = io.read_bytes - prev.read_bytes
            write_rate = io.write_bytes - prev.write_bytes
        else:
            read_rate = write_rate = 0

        # Format sizes
        total = format_size(usage.total)
        used = format_size(usage.used)
        free = format_size(usage.free)
        percent = f"{usage.percent}%"
        read_rate_str = format_size(read_rate) + "/s"
        write_rate_str = format_size(write_rate) + "/s"

        table.add_row(
            partition.device,
            partition.mountpoint,
            partition.fstype,
            total,
            used,
            free,
            percent,
            read_rate_str,
            write_rate_str,
        )

    return table, current_io

def format_size(size_bytes: int) -> str:
    """
    Convert a byte count into a human-readable string.
    Args:
        size_bytes (int): Size in bytes.
    Returns:
        str: Formatted size string.
    """
    if size_bytes == 0:
        return "0 B"
    size_names = ["B", "KB", "MB", "GB", "TB", "PB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.2f} {size_names[i]}"

# ------------------------------------------------------------------------------
# Main Monitoring Loop
# ------------------------------------------------------------------------------
def main() -> None:
    """
    Main entry point for the real-time storage analyzer.
    Sets up a live Rich display that updates disk usage and IO statistics every second.
    """
    logger.info("Starting Real-Time Hard Drive Storage Analyzer")
    console = Console()

    # Get initial IO counters
    previous_io = psutil.disk_io_counters(perdisk=True)
    
    # Use Rich Live to continuously update the table
    with Live(refresh_per_second=1, console=console, screen=True) as live:
        try:
            while True:
                # Build table and update previous IO
                table, current_io = get_disk_data(previous_io)
                previous_io = current_io
                # Update live display with current timestamp header
                header = Panel(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                               style="bold rgb(136,192,208)")
                live.update(Panel.fit(table, title=header.renderable))
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Exiting Real-Time Analyzer...")
            sys.exit(0)

if __name__ == "__main__":
    main()

