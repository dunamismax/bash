#!/usr/bin/env python3
"""
Enhanced System Log Monitor
---------------------------

A beautiful, interactive terminal-based utility for monitoring system log files
in real-time. This tool supports:
  • Monitoring multiple log files concurrently
  • Detecting patterns such as errors, warnings, and critical issues
  • Displaying color-coded outputs using a Nord-themed interface
  • Generating summary reports of detected issues
  • Exporting results to JSON or CSV formats

Note: Some operations may require root privileges.
Version: 1.0.0
"""

import atexit
import csv
import datetime
import json
import os
import re
import signal
import sys
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Pattern

import shutil
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn, TaskID
import pyfiglet

# ==============================
# Configuration & Constants
# ==============================
APP_NAME = "Enhanced System Log Monitor"
VERSION = "1.0.0"

DEFAULT_LOG_FILES = [
    "/var/log/syslog",
    "/var/log/auth.log",
    "/var/log/kern.log",
    "/var/log/apache2/error.log",
    "/var/log/nginx/error.log",
]

DEFAULT_PATTERNS: Dict[str, Dict[str, Any]] = {
    "critical": {
        "pattern": r"\b(critical|crit|emerg|alert|panic)\b",
        "description": "Critical system issues requiring immediate attention",
        "severity": 1,
    },
    "error": {
        "pattern": r"\b(error|err|failed|failure)\b",
        "description": "Errors that might affect system functionality",
        "severity": 2,
    },
    "warning": {
        "pattern": r"\b(warning|warn|could not)\b",
        "description": "Potential issues that might escalate",
        "severity": 3,
    },
    "notice": {
        "pattern": r"\b(notice|info|information)\b",
        "description": "Informational messages about system activity",
        "severity": 4,
    },
}

NETWORK_PATTERNS: Dict[str, Dict[str, Any]] = {
    "ssh_auth_failure": {
        "pattern": r"Failed password for|authentication failure",
        "description": "SSH authentication failures",
        "severity": 2,
    },
    "access_denied": {
        "pattern": r"(access denied|permission denied)",
        "description": "Permission issues for resources",
        "severity": 3,
    },
}

SUMMARY_INTERVAL = 30        # Seconds between summary reports
UPDATE_INTERVAL = 0.1        # Seconds between log file checks
ANIMATION_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
MAX_LINE_LENGTH = 120        # Maximum characters to display per log line
MAX_STORED_ENTRIES = 1000    # Maximum number of stored log matches

TERM_WIDTH = min(shutil.get_terminal_size().columns, 100)
TERM_HEIGHT = min(shutil.get_terminal_size().lines, 30)

# ==============================
# Nord-Themed Console Setup
# ==============================
console = Console()

class NordColors:
    """Nord theme color palette for consistent UI styling."""
    # Polar Night (background)
    NORD0 = "#2E3440"
    NORD1 = "#3B4252"
    NORD2 = "#434C5E"
    NORD3 = "#4C566A"
    # Snow Storm (foreground)
    NORD4 = "#D8DEE9"
    NORD5 = "#E5E9F0"
    NORD6 = "#ECEFF4"
    # Frost (blue accents)
    NORD7 = "#8FBCBB"
    NORD8 = "#88C0D0"
    NORD9 = "#81A1C1"
    NORD10 = "#5E81AC"
    # Aurora (status indicators)
    NORD11 = "#BF616A"  # Red – errors
    NORD12 = "#D08770"  # Orange – warnings
    NORD13 = "#EBCB8B"  # Yellow – caution
    NORD14 = "#A3BE8C"  # Green – success
    NORD15 = "#B48EAD"  # Purple – critical

# ==============================
# UI Helper Functions
# ==============================
def print_header(text: str) -> None:
    """Print a striking header using pyfiglet inside a Rich panel."""
    ascii_art = pyfiglet.figlet_format(text, font="slant")
    panel = Panel(ascii_art, style=f"bold {NordColors.NORD8}", border_style=NordColors.NORD8)
    console.print(panel)

def print_section(title: str) -> None:
    """Print a formatted section header."""
    border = "═" * TERM_WIDTH
    console.print(f"\n[bold {NordColors.NORD8}]{border}[/]")
    console.print(f"[bold {NordColors.NORD8}]{title.center(TERM_WIDTH)}[/]")
    console.print(f"[bold {NordColors.NORD8}]{border}[/]\n")

def print_info(message: str) -> None:
    """Display an informational message."""
    console.print(f"[{NordColors.NORD9}]{message}[/]")

def print_success(message: str) -> None:
    """Display a success message."""
    console.print(f"[bold {NordColors.NORD14}]✓ {message}[/]")

def print_warning(message: str) -> None:
    """Display a warning message."""
    console.print(f"[bold {NordColors.NORD13}]⚠ {message}[/]")

def print_error(message: str) -> None:
    """Display an error message."""
    console.print(f"[bold {NordColors.NORD11}]✗ {message}[/]")

def print_step(text: str) -> None:
    """Print a step description."""
    console.print(f"[{NordColors.NORD8}]• {text}[/]")

def clear_screen() -> None:
    """Clear the terminal screen."""
    console.clear()

def pause() -> None:
    """Pause execution until the user presses Enter."""
    console.input(f"\n[{NordColors.NORD15}]Press Enter to continue...[/]")

def get_user_input(prompt: str, default: str = "") -> str:
    """Prompt the user for input with a styled message."""
    return Prompt.ask(f"[bold {NordColors.NORD15}]{prompt}[/]", default=default)

def get_user_choice(prompt: str, choices: List[str]) -> str:
    """Prompt the user to choose from a list of options."""
    return Prompt.ask(f"[bold {NordColors.NORD15}]{prompt}[/]", choices=choices, show_choices=True)

def get_user_confirmation(prompt: str) -> bool:
    """Prompt the user for a Yes/No confirmation."""
    return Confirm.ask(f"[bold {NordColors.NORD15}]{prompt}[/]")

def create_menu_table(title: str, options: List[tuple]) -> Table:
    """Generate a table for menu options."""
    table = Table(title=title, box=None, title_style=f"bold {NordColors.NORD8}")
    table.add_column("Option", style=f"{NordColors.NORD9}", justify="right")
    table.add_column("Description", style=f"{NordColors.NORD4}")
    for key, desc in options:
        table.add_row(key, desc)
    return table

def truncate_line(line: str, max_length: int = MAX_LINE_LENGTH) -> str:
    """Truncate a log line to a maximum length."""
    return line if len(line) <= max_length else line[:max_length - 3] + "..."

def format_timestamp(timestamp: Optional[float] = None) -> str:
    """Convert a timestamp to a human-readable string."""
    if timestamp is None:
        timestamp = time.time()
    return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")

# ==============================
# System Helper Functions
# ==============================
def check_root_privileges() -> bool:
    """Return True if the script is run with root privileges."""
    return os.geteuid() == 0

def warn_if_not_root() -> None:
    """Warn the user if root privileges are not present."""
    if not check_root_privileges():
        print_warning("Running without root privileges – some log files may be inaccessible.")

# ==============================
# Signal Handling & Cleanup
# ==============================
def cleanup() -> None:
    """Perform any necessary cleanup tasks before exit."""
    print_step("Performing cleanup tasks...")
    # (Add additional cleanup here if needed)

atexit.register(cleanup)

def signal_handler(signum, frame) -> None:
    """Handle termination signals gracefully."""
    sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else f"signal {signum}"
    print_warning(f"\nScript interrupted by {sig_name}.")
    cleanup()
    sys.exit(128 + signum)

for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)

# ==============================
# Data Classes & Log Statistics
# ==============================
@dataclass
class LogPattern:
    """Represents a regex pattern for log monitoring."""
    name: str
    pattern: Pattern
    description: str
    severity: int

@dataclass
class LogMatch:
    """Represents a match of a log pattern."""
    timestamp: float
    log_file: str
    pattern_name: str
    severity: int
    line: str

class LogStatistics:
    """Tracks statistics about processed log lines and pattern matches."""
    def __init__(self) -> None:
        self.total_lines: int = 0
        self.total_matches: int = 0
        self.pattern_matches: Dict[str, int] = defaultdict(int)
        self.file_matches: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.severity_counts: Dict[int, int] = defaultdict(int)
        self.start_time: float = time.time()
        self.lock = threading.Lock()

    def increment_lines(self) -> None:
        with self.lock:
            self.total_lines += 1

    def update(self, log_file: str, pattern_name: str, severity: int) -> None:
        with self.lock:
            self.total_matches += 1
            self.pattern_matches[pattern_name] += 1
            self.file_matches[log_file][pattern_name] += 1
            self.severity_counts[severity] += 1

# ==============================
# Progress Tracking Classes
# ==============================
class ProgressManager:
    """Unified progress tracking using Rich Progress."""
    def __init__(self):
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold {task.fields[color]}]{task.description}"),
            BarColumn(bar_width=None),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("[{task.fields[status]}]"),
            TimeRemainingColumn(),
            console=console,
            expand=True,
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.progress.stop()

    def add_task(self, description: str, total: float, color: str = NordColors.NORD8) -> TaskID:
        return self.progress.add_task(
            description, total=total, color=color, status=f"{NordColors.NORD9}starting"
        )

    def update(self, task_id: TaskID, advance: float = 0, **kwargs) -> None:
        self.progress.update(task_id, advance=advance, **kwargs)

    def start(self):
        self.progress.start()

    def stop(self):
        self.progress.stop()

class Spinner:
    """A simple, thread-safe spinner for indeterminate progress."""
    def __init__(self, message: str):
        self.message = message
        self.spinner_chars = ANIMATION_FRAMES
        self.current = 0
        self.spinning = False
        self.thread: Optional[threading.Thread] = None
        self.start_time = 0
        self._lock = threading.Lock()

    def _spin(self) -> None:
        while self.spinning:
            elapsed = time.time() - self.start_time
            time_str = format_time(elapsed)
            with self._lock:
                console.print(
                    f"\r[{NordColors.NORD10}]{self.spinner_chars[self.current]}[/] "
                    f"[{NordColors.NORD8}]{self.message}[/] "
                    f"[[dim]elapsed: {time_str}[/dim]]",
                    end="",
                )
                self.current = (self.current + 1) % len(self.spinner_chars)
            time.sleep(0.1)
            
    def start(self) -> None:
        with self._lock:
            self.spinning = True
            self.start_time = time.time()
            self.thread = threading.Thread(target=self._spin, daemon=True)
            self.thread.start()

    def stop(self, success: bool = True) -> None:
        with self._lock:
            self.spinning = False
            if self.thread:
                self.thread.join()
            elapsed = time.time() - self.start_time
            time_str = format_time(elapsed)
            console.print("\r" + " " * TERM_WIDTH, end="\r")
            if success:
                console.print(f"[{NordColors.NORD14}]✓[/] [{NordColors.NORD8}]{self.message}[/] "
                              f"[{NordColors.NORD14}]completed[/] in {time_str}")
            else:
                console.print(f"[{NordColors.NORD11}]✗[/] [{NordColors.NORD8}]{self.message}[/] "
                              f"[{NordColors.NORD11}]failed[/] after {time_str}")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop(success=exc_type is None)

def format_time(seconds: float) -> str:
    """Format seconds into a readable time string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f}m"
    else:
        return f"{seconds / 3600:.1f}h"

# ==============================
# Core Log Monitor Class
# ==============================
class LogMonitor:
    """
    Monitors a list of log files for specified patterns in real time.
    Supports live summary reporting and export of matched log entries.
    """
    def __init__(
        self,
        log_files: List[str],
        pattern_configs: Dict[str, Dict[str, Any]] = None,
        max_stored_entries: int = MAX_STORED_ENTRIES,
        summary_interval: int = SUMMARY_INTERVAL,
    ) -> None:
        self.log_files = log_files
        self.max_stored_entries = max_stored_entries
        self.summary_interval = summary_interval
        self.patterns: Dict[str, LogPattern] = {}
        pattern_configs = pattern_configs or DEFAULT_PATTERNS
        for name, config in pattern_configs.items():
            self.patterns[name] = LogPattern(
                name=name,
                pattern=re.compile(config["pattern"], re.IGNORECASE),
                description=config["description"],
                severity=config["severity"],
            )
        self.stats = LogStatistics()
        self.matches: List[LogMatch] = []
        self.file_positions: Dict[str, int] = {}
        self.matches_lock = threading.Lock()
        self.file_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.quiet_mode = False
        self.last_summary_time = 0
        self.animation_index = 0
        self.shutdown_flag = False

    def _process_log_file(self, log_path: str) -> None:
        """Continuously monitor a single log file for new lines and pattern matches."""
        try:
            if not os.path.exists(log_path):
                print_warning(f"Log file not found: {log_path}")
                return
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                with self.file_lock:
                    if log_path not in self.file_positions:
                        self.file_positions[log_path] = os.path.getsize(log_path)
                    f.seek(self.file_positions[log_path])
                while not self.stop_event.is_set():
                    lines = f.readlines()
                    if not lines:
                        with self.file_lock:
                            self.file_positions[log_path] = f.tell()
                        time.sleep(UPDATE_INTERVAL)
                        continue
                    for line in lines:
                        self.stats.increment_lines()
                        line = line.strip()
                        for name, pattern_obj in self.patterns.items():
                            if pattern_obj.pattern.search(line):
                                timestamp = time.time()
                                match = LogMatch(
                                    timestamp=timestamp,
                                    log_file=log_path,
                                    pattern_name=name,
                                    severity=pattern_obj.severity,
                                    line=line,
                                )
                                self.stats.update(log_path, name, pattern_obj.severity)
                                with self.matches_lock:
                                    self.matches.append(match)
                                    if len(self.matches) > self.max_stored_entries:
                                        self.matches.pop(0)
                                if not self.quiet_mode:
                                    self._display_match(match)
                    with self.file_lock:
                        self.file_positions[log_path] = f.tell()
        except PermissionError:
            print_error(f"Permission denied: {log_path}. Try running as root.")
        except Exception as e:
            print_error(f"Error monitoring {log_path}: {e}")

    def _display_match(self, match: LogMatch) -> None:
        """Display a matched log line with timestamp, pattern tag, and filename."""
        color = self._get_severity_color(match.severity)
        timestamp = format_timestamp(match.timestamp)
        filename = Path(match.log_file).name
        line = truncate_line(match.line)
        console.print(f"[dim]{timestamp}[/dim] [bold {color}][{match.pattern_name.upper()}][/bold {color}] "
                      f"([italic]{filename}[/italic]): {line}")

    def _get_severity_color(self, severity: int) -> str:
        """Return a Nord-themed color based on the severity level."""
        if severity == 1:
            return NordColors.NORD15  # Critical – Purple
        elif severity == 2:
            return NordColors.NORD11  # Error – Red
        elif severity == 3:
            return NordColors.NORD13  # Warning – Yellow
        elif severity == 4:
            return NordColors.NORD7   # Notice – Light Blue
        return NordColors.NORD4      # Default – Light Grey

    def _display_activity_indicator(self) -> None:
        """Display a live animated indicator of log monitoring activity."""
        self.animation_index = (self.animation_index + 1) % len(ANIMATION_FRAMES)
        indicator = ANIMATION_FRAMES[self.animation_index]
        console.print(f"\r[dim]{indicator} Monitoring {len(self.log_files)} log file(s)... "
                      f"({self.stats.total_matches} matches, {self.stats.total_lines} lines)[/dim]", end="")

    def _print_summary(self, force: bool = False) -> None:
        """Display a summary report of log statistics if enough time has passed."""
        now = time.time()
        if not force and now - self.last_summary_time < self.summary_interval:
            return
        self.last_summary_time = now
        console.print("\r" + " " * TERM_WIDTH, end="\r")
        if not self.stats.total_matches and not force:
            return

        elapsed = now - self.stats.start_time
        elapsed_str = f"{int(elapsed // 3600)}h {int((elapsed % 3600) // 60)}m {int(elapsed % 60)}s"
        print_section("Log Monitor Summary")
        console.print(f"Monitoring Duration: [bold {NordColors.NORD4}]{elapsed_str}[/bold {NordColors.NORD4}]")
        console.print(f"Total Lines Processed: [bold {NordColors.NORD4}]{self.stats.total_lines}[/bold {NordColors.NORD4}]")
        console.print(f"Total Matches: [bold {NordColors.NORD4}]{self.stats.total_matches}[/bold {NordColors.NORD4}]")

        if self.stats.severity_counts:
            console.print(f"\n[bold {NordColors.NORD8}]Severity Breakdown:[/bold {NordColors.NORD8}]")
            for severity in sorted(self.stats.severity_counts.keys()):
                count = self.stats.severity_counts[severity]
                color = self._get_severity_color(severity)
                severity_name = {1: "Critical", 2: "Error", 3: "Warning", 4: "Notice"}.get(severity, f"Level {severity}")
                console.print(f"  [bold {color}]{severity_name}: {count}[/bold {color}]")

        if self.stats.pattern_matches:
            console.print(f"\n[bold {NordColors.NORD8}]Pattern Matches:[/bold {NordColors.NORD8}]")
            for pattern, count in sorted(self.stats.pattern_matches.items(), key=lambda x: x[1], reverse=True):
                pattern_obj = self.patterns.get(pattern)
                if pattern_obj:
                    color = self._get_severity_color(pattern_obj.severity)
                    console.print(f"  [bold {color}]{pattern.upper()}: {count}[/bold {color}]")

        if self.stats.file_matches:
            console.print(f"\n[bold {NordColors.NORD8}]Log File Activity:[/bold {NordColors.NORD8}]")
            for log_file, patterns in self.stats.file_matches.items():
                total = sum(patterns.values())
                filename = Path(log_file).name
                console.print(f"  [{NordColors.NORD4}]{filename}[/{NordColors.NORD4}]: {total} matches")
                for pattern, count in sorted(patterns.items(), key=lambda x: x[1], reverse=True)[:3]:
                    pattern_obj = self.patterns.get(pattern)
                    if pattern_obj:
                        color = self._get_severity_color(pattern_obj.severity)
                        console.print(f"    [bold {color}]{pattern.upper()}: {count}[/bold {color}]")
        console.print("")

    def export_results(self, export_format: str, output_file: str) -> bool:
        """Export collected log matches to JSON or CSV format."""
        with self.matches_lock:
            matches_copy = list(self.matches)
        if not matches_copy:
            print_warning("No matches to export.")
            return False
        try:
            if export_format.lower() == "json":
                serializable = [{
                    "timestamp": format_timestamp(match.timestamp),
                    "log_file": match.log_file,
                    "pattern": match.pattern_name,
                    "severity": match.severity,
                    "line": match.line
                } for match in matches_copy]
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(serializable, f, indent=2)
            elif export_format.lower() == "csv":
                with open(output_file, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["Timestamp", "Log File", "Pattern", "Severity", "Line"])
                    for match in matches_copy:
                        writer.writerow([
                            format_timestamp(match.timestamp),
                            match.log_file,
                            match.pattern_name,
                            match.severity,
                            match.line,
                        ])
            else:
                print_error(f"Unsupported export format: {export_format}")
                return False
            print_success(f"Exported {len(matches_copy)} matches to {output_file}")
            return True
        except Exception as e:
            print_error(f"Export failed: {e}")
            return False

    def start_monitoring(self, quiet: bool = False, stats_only: bool = False) -> None:
        """Start monitoring the configured log files concurrently."""
        self.quiet_mode = quiet or stats_only
        self.shutdown_flag = False

        clear_screen()
        print_header("Log Monitor")
        print_info(f"Starting log monitor at: {format_timestamp()}")
        print_info(f"Monitoring {len(self.log_files)} log file(s)")
        print_info(f"Tracking {len(self.patterns)} pattern(s)")
        print_info("Press Ctrl+C to stop monitoring\n")
        warn_if_not_root()

        # Report which log files are accessible
        for log_file in self.log_files:
            if os.path.exists(log_file) and os.access(log_file, os.R_OK):
                print_success(f"Monitoring: {log_file}")
            else:
                print_error(f"Cannot access: {log_file}")
        console.print("")

        threads = []
        for log_file in self.log_files:
            thread = threading.Thread(target=self._process_log_file, args=(log_file,), daemon=True)
            thread.start()
            threads.append(thread)

        try:
            while not self.shutdown_flag:
                if not stats_only:
                    self._display_activity_indicator()
                if not stats_only:
                    self._print_summary()
                time.sleep(0.5)
        except KeyboardInterrupt:
            self.shutdown_flag = True
        finally:
            self.stop_event.set()
            if self.stats.total_matches > 0 or stats_only:
                self._print_summary(force=True)
            print_success("\nLog monitoring completed")
            for thread in threads:
                thread.join(timeout=0.5)

    def stop_monitoring(self) -> None:
        """Signal the monitoring threads to stop."""
        self.shutdown_flag = True
        self.stop_event.set()

# ==============================
# Menu Functions
# ==============================
def select_log_files_menu() -> List[str]:
    """Menu for selecting log files to monitor."""
    print_section("Select Log Files")
    print_info("Choose log files to monitor from the defaults below:")

    table = Table(title="Default Log Files", box=None, title_style=f"bold {NordColors.NORD8}")
    table.add_column("Option", style=f"{NordColors.NORD9}", justify="right")
    table.add_column("Log File", style=f"{NordColors.NORD4}")
    table.add_column("Status", style=f"{NordColors.NORD14}")

    for i, log_file in enumerate(DEFAULT_LOG_FILES, 1):
        status = "Available" if os.path.exists(log_file) and os.access(log_file, os.R_OK) else "Not accessible"
        status_color = NordColors.NORD14 if "Available" in status else NordColors.NORD11
        table.add_row(str(i), log_file, f"[{status_color}]{status}[/{status_color}]")
    console.print(table)

    selected_files = []
    while True:
        options = [
            ("1-9", "Select logs by number (comma-separated)"),
            ("a", "Select all available default logs"),
            ("c", "Add custom log file path"),
            ("s", "Show selected logs"),
            ("d", "Done selecting"),
        ]
        console.print(create_menu_table("Options", options))
        choice = get_user_input("Enter your choice:").lower()

        if choice == "a":
            for log_file in DEFAULT_LOG_FILES:
                if os.path.exists(log_file) and os.access(log_file, os.R_OK) and log_file not in selected_files:
                    selected_files.append(log_file)
            print_success(f"Added all available default logs ({len(selected_files)} selected).")
        elif choice == "c":
            custom_path = get_user_input("Enter the full path to the log file:")
            if os.path.exists(custom_path):
                if os.access(custom_path, os.R_OK):
                    if custom_path not in selected_files:
                        selected_files.append(custom_path)
                        print_success(f"Added: {custom_path}")
                    else:
                        print_warning(f"Log file already selected: {custom_path}")
                else:
                    print_error(f"Cannot read file: {custom_path}. Check permissions.")
            else:
                print_error(f"File not found: {custom_path}")
        elif choice == "s":
            if selected_files:
                print_section("Currently Selected Logs")
                for i, log_file in enumerate(selected_files, 1):
                    print_info(f"{i}. {log_file}")
            else:
                print_warning("No logs selected yet.")
        elif choice == "d":
            if not selected_files:
                print_warning("Please select at least one log file.")
            else:
                break
        elif "," in choice or choice.isdigit():
            try:
                indices = [int(i.strip()) for i in choice.split(",") if i.strip().isdigit()]
                for idx in indices:
                    if 1 <= idx <= len(DEFAULT_LOG_FILES):
                        log_file = DEFAULT_LOG_FILES[idx - 1]
                        if os.path.exists(log_file) and os.access(log_file, os.R_OK):
                            if log_file not in selected_files:
                                selected_files.append(log_file)
                                print_success(f"Added: {log_file}")
                            else:
                                print_warning(f"Already selected: {log_file}")
                        else:
                            print_error(f"Cannot access file: {log_file}")
                    else:
                        print_error(f"Invalid option: {idx}")
            except ValueError:
                print_error("Invalid input. Please enter numbers or comma-separated numbers.")
        else:
            print_error("Invalid choice. Please try again.")
    return selected_files

def configure_patterns_menu() -> Dict[str, Dict[str, Any]]:
    """Menu for configuring log patterns."""
    print_section("Configure Patterns")
    all_patterns = DEFAULT_PATTERNS.copy()
    all_patterns.update(NETWORK_PATTERNS)
    selected_patterns = all_patterns.copy()

    while True:
        table = Table(title="Current Pattern Configuration", box=None, title_style=f"bold {NordColors.NORD8}")
        table.add_column("Name", style=f"{NordColors.NORD9}")
        table.add_column("Regex Pattern", style=f"{NordColors.NORD4}")
        table.add_column("Severity", style=f"{NordColors.NORD13}", justify="center")
        table.add_column("Status", style=f"{NordColors.NORD14}")
        for name, config in selected_patterns.items():
            severity_color = {1: NordColors.NORD15, 2: NordColors.NORD11, 3: NordColors.NORD13, 4: NordColors.NORD7}.get(config["severity"], NordColors.NORD4)
            status = "✓"
            table.add_row(name.upper(), truncate_line(config["pattern"], 40), f"[{severity_color}]{config['severity']}[/{severity_color}]", f"[{NordColors.NORD14}]{status}[/{NordColors.NORD14}]")
        console.print(table)

        options = [
            ("a", "Add custom pattern"),
            ("e", "Edit existing pattern"),
            ("r", "Remove pattern"),
            ("d", "Done configuring patterns"),
        ]
        console.print(create_menu_table("Options", options))
        choice = get_user_input("Enter your choice:").lower()
        if choice == "a":
            name = get_user_input("Enter pattern name (no spaces):").strip()
            if not name or " " in name or name in selected_patterns:
                print_error("Invalid or duplicate pattern name.")
                continue
            pattern = get_user_input("Enter regex pattern:").strip()
            if not pattern:
                print_error("Pattern cannot be empty.")
                continue
            try:
                re.compile(pattern)
            except re.error as e:
                print_error(f"Invalid regex: {e}")
                continue
            try:
                severity = int(get_user_input("Enter severity (1-4, 1 is highest):"))
                if not 1 <= severity <= 4:
                    print_error("Severity must be between 1 and 4.")
                    continue
            except ValueError:
                print_error("Severity must be a number between 1 and 4.")
                continue
            description = get_user_input("Enter pattern description:")
            selected_patterns[name] = {"pattern": pattern, "description": description, "severity": severity}
            print_success(f"Added pattern: {name}")
        elif choice == "e":
            name = get_user_input("Enter pattern name to edit:").strip()
            if name not in selected_patterns:
                print_error(f"Pattern '{name}' not found.")
                continue
            pattern = get_user_input("Enter new regex pattern (leave empty to keep current):").strip()
            if pattern:
                try:
                    re.compile(pattern)
                    selected_patterns[name]["pattern"] = pattern
                except re.error as e:
                    print_error(f"Invalid regex: {e}")
                    continue
            severity_input = get_user_input(f"Enter new severity (current: {selected_patterns[name]['severity']}, leave empty to keep):")
            if severity_input:
                try:
                    severity = int(severity_input)
                    if not 1 <= severity <= 4:
                        print_error("Severity must be between 1 and 4.")
                        continue
                    selected_patterns[name]["severity"] = severity
                except ValueError:
                    print_error("Invalid severity value.")
                    continue
            description = get_user_input("Enter new description (leave empty to keep current):")
            if description:
                selected_patterns[name]["description"] = description
            print_success(f"Updated pattern: {name}")
        elif choice == "r":
            name = get_user_input("Enter pattern name to remove:").strip()
            if name not in selected_patterns:
                print_error(f"Pattern '{name}' not found.")
                continue
            if get_user_confirmation(f"Are you sure you want to remove pattern '{name}'?"):
                del selected_patterns[name]
                print_success(f"Removed pattern: {name}")
        elif choice == "d":
            break
        else:
            print_error("Invalid choice. Please try again.")
    return selected_patterns

def export_options_menu(monitor: LogMonitor) -> None:
    """Menu for exporting monitoring results."""
    if not monitor.matches:
        print_warning("No log matches to export.")
        pause()
        return
    print_section("Export Options")
    print_info(f"Total matches available: {len(monitor.matches)}")
    export_options = [("1", "Export to JSON"), ("2", "Export to CSV"), ("0", "Cancel")]
    console.print(create_menu_table("Export Format", export_options))
    choice = get_user_input("Select export format:")
    if choice == "0":
        return
    if choice not in ["1", "2"]:
        print_error("Invalid choice.")
        pause()
        return
    export_format = "json" if choice == "1" else "csv"
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    default_filename = f"log_monitor_results_{timestamp}.{export_format}"
    output_file = get_user_input(f"Enter output filename (default: {default_filename}):", default_filename)
    with Spinner(f"Exporting data to {export_format.upper()}") as spinner:
        success = monitor.export_results(export_format, output_file)
        spinner.stop(success=success)
    pause()

def monitor_settings_menu() -> Dict[str, Any]:
    """Menu for configuring monitoring settings."""
    print_section("Monitoring Settings")
    settings = {
        "quiet_mode": False,
        "stats_only": False,
        "summary_interval": SUMMARY_INTERVAL,
        "max_stored_entries": MAX_STORED_ENTRIES,
    }
    while True:
        print_info("Current Settings:")
        print_info(f"  • Quiet Mode: {'Yes' if settings['quiet_mode'] else 'No'}")
        print_info(f"  • Stats Only: {'Yes' if settings['stats_only'] else 'No'}")
        print_info(f"  • Summary Interval: {settings['summary_interval']} seconds")
        print_info(f"  • Max Stored Entries: {settings['max_stored_entries']}")
        options = [
            ("1", "Toggle Quiet Mode"),
            ("2", "Toggle Stats Only Mode"),
            ("3", "Change Summary Interval"),
            ("4", "Change Max Stored Entries"),
            ("0", "Save and Return"),
        ]
        console.print(create_menu_table("Options", options))
        choice = get_user_input("Enter your choice:")
        if choice == "1":
            settings["quiet_mode"] = not settings["quiet_mode"]
            print_success(f"Quiet Mode {'Enabled' if settings['quiet_mode'] else 'Disabled'}")
        elif choice == "2":
            settings["stats_only"] = not settings["stats_only"]
            print_success(f"Stats Only Mode {'Enabled' if settings['stats_only'] else 'Disabled'}")
        elif choice == "3":
            try:
                interval = int(get_user_input("Enter summary interval in seconds (10-600):"))
                if not 10 <= interval <= 600:
                    print_error("Interval must be between 10 and 600 seconds.")
                    continue
                settings["summary_interval"] = interval
                print_success(f"Summary interval set to {interval} seconds.")
            except ValueError:
                print_error("Please enter a valid number.")
        elif choice == "4":
            try:
                max_entries = int(get_user_input("Enter max stored entries (100-10000):"))
                if not 100 <= max_entries <= 10000:
                    print_error("Value must be between 100 and 10000.")
                    continue
                settings["max_stored_entries"] = max_entries
                print_success(f"Max stored entries set to {max_entries}.")
            except ValueError:
                print_error("Please enter a valid number.")
        elif choice == "0":
            break
        else:
            print_error("Invalid choice. Please try again.")
    return settings

def main_menu() -> None:
    """Display the main menu and handle user interactions."""
    log_monitor = None
    log_files = []
    pattern_configs = DEFAULT_PATTERNS.copy()

    while True:
        clear_screen()
        print_header(APP_NAME)
        print_info(f"Version: {VERSION}")
        uname = os.uname()
        print_info(f"System: {uname.sysname} {uname.release}")
        print_info(f"Running as root: {'Yes' if check_root_privileges() else 'No'}")
        print_info(f"Time: {format_timestamp()}")
        if not check_root_privileges():
            print_warning("Some log files may require root privileges.")
        menu_options = [
            ("1", "Select Log Files to Monitor"),
            ("2", "Configure Pattern Detection"),
            ("3", "Configure Monitoring Settings"),
            ("4", "Start Monitoring"),
            ("5", "Export Current Results"),
            ("0", "Exit"),
        ]
        console.print(create_menu_table("Main Menu", menu_options))
        if log_files:
            print_info(f"\nCurrently monitoring {len(log_files)} log file(s).")
        choice = get_user_input("Enter your choice (0-5):")
        if choice == "1":
            log_files = select_log_files_menu()
        elif choice == "2":
            pattern_configs = configure_patterns_menu()
        elif choice == "3":
            settings = monitor_settings_menu()
            global SUMMARY_INTERVAL
            SUMMARY_INTERVAL = settings["summary_interval"]
        elif choice == "4":
            if not log_files:
                print_error("No log files selected for monitoring.")
                pause()
                continue
            log_monitor = LogMonitor(log_files, pattern_configs, max_stored_entries=MAX_STORED_ENTRIES, summary_interval=SUMMARY_INTERVAL)
            settings = monitor_settings_menu()
            try:
                log_monitor.start_monitoring(quiet=settings["quiet_mode"], stats_only=settings["stats_only"])
            except KeyboardInterrupt:
                pass
            finally:
                pause()
        elif choice == "5":
            if log_monitor is None or not log_monitor.matches:
                print_warning("No monitoring data available to export.")
                pause()
            else:
                export_options_menu(log_monitor)
        elif choice == "0":
            if log_monitor and not log_monitor.stop_event.is_set():
                if get_user_confirmation("Monitoring is still active. Are you sure you want to exit?"):
                    log_monitor.stop_monitoring()
                else:
                    continue
            clear_screen()
            print_header("Goodbye!")
            print_info("Thank you for using the Enhanced System Log Monitor.")
            time.sleep(1)
            sys.exit(0)
        else:
            print_error("Invalid selection. Please try again.")
            time.sleep(1)

# ==============================
# Main Entry Point
# ==============================
def main() -> None:
    """Main entry point for the log monitor."""
    try:
        signal.signal(signal.SIGINT, signal_handler)
        main_menu()
    except KeyboardInterrupt:
        print_warning("\nProcess interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()