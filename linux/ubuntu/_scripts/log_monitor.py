#!/usr/bin/env python3
"""
Ubuntu System Log Monitor & Analyzer
--------------------------------------
Description:
  This tool continuously monitors and scans essential system log files on Ubuntu,
  including:
    - syslog (/var/log/syslog)
    - auth.log (/var/log/auth.log)
    - Plex Media Server logs (default: /var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Logs/Plex Media Server.log)
    - Caddy logs (default: /var/log/caddy/access.log)

  It analyzes new log entries for critical patterns (e.g., error, critical, fail, warning, panic)
  and triggers notifications (or automated fixes) when issues are detected.
  A dynamic dashboard displays real-time summaries and trends using rich console tables.

Usage:
  sudo ./log_monitor.py [--syslog PATH] [--authlog PATH] [--plex PATH] [--caddy PATH]

Author: Your Name | License: MIT | Version: 1.0.0
"""

import argparse
import atexit
import logging
import os
import re
import signal
import sys
import time
from collections import defaultdict
from threading import Thread, Event

from rich.console import Console
from rich.live import Live
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

# ------------------------------------------------------------------------------
# Environment Configuration & Nord Color Palette (24-bit ANSI sequences)
# ------------------------------------------------------------------------------
LOG_FILE = "/var/log/ubuntu_log_monitor.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"

NORD0 = "\033[38;2;46;52;64m"
NORD1 = "\033[38;2;59;66;82m"
NORD8 = "\033[38;2;136;192;208m"
NORD9 = "\033[38;2;129;161;193m"
NORD10 = "\033[38;2;94;129;172m"
NORD11 = "\033[38;2;191;97;106m"
NORD13 = "\033[38;2;235;203;139m"
NORD14 = "\033[38;2;163;190;140m"
NC = "\033[0m"

# Default log file paths; allow overrides via CLI arguments
DEFAULT_SYSLOG = "/var/log/syslog"
DEFAULT_AUTHLOG = "/var/log/auth.log"
DEFAULT_PLEXLOG = "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Logs/Plex Media Server.log"
DEFAULT_CADDYLOG = "/var/log/caddy/access.log"

# ------------------------------------------------------------------------------
# PATTERNS TO MONITOR (compiled regex patterns)
# ------------------------------------------------------------------------------
DEFAULT_PATTERNS = {
    "error": re.compile(r"\berror\b", re.IGNORECASE),
    "critical": re.compile(r"\bcritical\b", re.IGNORECASE),
    "fail": re.compile(r"\bfail(?:ed|ure)?\b", re.IGNORECASE),
    "warning": re.compile(r"\bwarning\b", re.IGNORECASE),
    "panic": re.compile(r"\bpanic\b", re.IGNORECASE),
}

# ------------------------------------------------------------------------------
# GLOBAL DATA STRUCTURES
# ------------------------------------------------------------------------------
# summary_counts will keep counts of detected patterns per log source
summary_counts = defaultdict(lambda: defaultdict(int))
# stop_event is used to signal threads to gracefully exit
stop_event = Event()


# ------------------------------------------------------------------------------
# CUSTOM LOGGING CONFIGURATION (using Nord color theme)
# ------------------------------------------------------------------------------
class NordColorFormatter(logging.Formatter):
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
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    console_formatter = NordColorFormatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    file_formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    try:
        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logging.warning(f"Failed to set up log file {LOG_FILE}: {e}")
    return logger


# ------------------------------------------------------------------------------
# SIGNAL HANDLING & CLEANUP
# ------------------------------------------------------------------------------
def signal_handler(signum, frame):
    sig_name = (
        signal.Signals(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )
    logging.error(f"Script interrupted by {sig_name}. Initiating shutdown...")
    stop_event.set()
    time.sleep(0.5)
    sys.exit(0)


for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)


def cleanup():
    logging.info("Performing cleanup before exit.")
    # Additional cleanup tasks can be added here


atexit.register(cleanup)


# ------------------------------------------------------------------------------
# ALERTING & AUTOMATED FIXES
# ------------------------------------------------------------------------------
def alert_notification(log_name: str, line: str, pattern_name: str):
    """
    Alert function triggered when a log line matches a pattern.
    It displays an alert message and (optionally) triggers an automated fix.
    """
    console = Console()
    alert_msg = f"[{NORD11}ALERT{NC}] {log_name} detected [{pattern_name.upper()}] in line: {line.strip()}"
    logging.error(alert_msg)
    console.print(alert_msg, style="bold red")

    # Placeholder for automated fix logic (if desired)
    if pattern_name in ("critical",):
        automated_fix(log_name, pattern_name)


def automated_fix(log_name: str, pattern_name: str):
    """
    Stub function for automated fix logic. Implement any automated remediation here.
    """
    fix_msg = (
        f"Automated fix triggered for {log_name} due to {pattern_name.upper()} issue."
    )
    logging.info(fix_msg)
    Console().print(fix_msg, style="bold yellow")
    # Example: os.system("service some_service restart")
    # Implement actual fix logic as needed


# ------------------------------------------------------------------------------
# LOG TAILING FUNCTION
# ------------------------------------------------------------------------------
def tail_log_file(log_name: str, file_path: str, patterns: dict):
    """
    Tails the given log file and checks each new line for defined patterns.
    Updates the summary_counts and triggers alerts on matches.
    """
    logging.info(f"Starting to monitor [{log_name}] at {file_path}")
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            # Seek to the end of file
            f.seek(0, os.SEEK_END)
            while not stop_event.is_set():
                line = f.readline()
                if not line:
                    time.sleep(0.1)
                    continue
                # Check each pattern against the new line
                for pattern_name, regex in patterns.items():
                    if regex.search(line):
                        summary_counts[log_name][pattern_name] += 1
                        alert_notification(log_name, line, pattern_name)
    except FileNotFoundError:
        logging.error(f"Log file not found: {file_path}")
    except Exception as e:
        logging.error(f"Error monitoring {file_path}: {e}")


# ------------------------------------------------------------------------------
# DASHBOARD & SUMMARY DISPLAY (using rich Live)
# ------------------------------------------------------------------------------
def generate_dashboard_table():
    """
    Generates a rich Table summarizing pattern counts per log file.
    """
    table = Table(title="Live Log Summary", style=NORD10)
    table.add_column("Log Source", style="bold")
    table.add_column("Pattern", justify="center")
    table.add_column("Count", justify="right")
    # For each monitored log, list counts for each pattern
    for log_source, counts in summary_counts.items():
        if counts:
            for pattern, count in counts.items():
                table.add_row(log_source, pattern, str(count))
        else:
            table.add_row(log_source, "-", "0")
    return table


def dashboard_live():
    """
    Continuously updates the live dashboard with current summary counts.
    """
    console = Console()
    with Live(
        generate_dashboard_table(), console=console, refresh_per_second=1
    ) as live:
        while not stop_event.is_set():
            live.update(generate_dashboard_table())
            time.sleep(1)


# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Ubuntu System Log Monitor & Analyzer")
    parser.add_argument("--syslog", default=DEFAULT_SYSLOG, help="Path to syslog")
    parser.add_argument("--authlog", default=DEFAULT_AUTHLOG, help="Path to auth.log")
    parser.add_argument(
        "--plex", default=DEFAULT_PLEXLOG, help="Path to Plex Media Server log"
    )
    parser.add_argument("--caddy", default=DEFAULT_CADDYLOG, help="Path to Caddy log")
    args = parser.parse_args()

    setup_logging()

    # Use a progress spinner during startup initialization
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task("Initializing log monitor...", total=None)
        time.sleep(1)  # Simulate initialization delay
        progress.update(task, description="Initialization complete.")

    # Start dashboard thread for live summaries
    dashboard_thread = Thread(target=dashboard_live, daemon=True)
    dashboard_thread.start()

    # Start a thread for each log file to monitor
    threads = []
    log_sources = {
        "syslog": args.syslog,
        "auth": args.authlog,
        "plex": args.plex,
        "caddy": args.caddy,
    }
    for log_name, file_path in log_sources.items():
        t = Thread(
            target=tail_log_file,
            args=(log_name, file_path, DEFAULT_PATTERNS),
            daemon=True,
        )
        threads.append(t)
        t.start()

    logging.info("Log monitor is now running. Press Ctrl+C to exit.")
    try:
        while not stop_event.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        stop_event.set()
        logging.info("Shutdown requested by user. Exiting...")
    for t in threads:
        t.join()
    dashboard_thread.join()


if __name__ == "__main__":
    main()
