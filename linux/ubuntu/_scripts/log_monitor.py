#!/usr/bin/env python3
"""
Enhanced System Log Monitor

This utility monitors system log files in real‑time, detecting and reporting important patterns such as errors,
warnings, and critical messages. It provides color‑coded output, detailed summaries, custom pattern detection,
and export capabilities (JSON or CSV). Some logs may require root privileges.

Usage:
  python log_monitor.py [options] [log files...]
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
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Pattern

import click
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
)
import pyfiglet

# ------------------------------
# Configuration & Constants
# ------------------------------
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

SUMMARY_INTERVAL = 30  # Seconds between summary reports
UPDATE_INTERVAL = 0.1  # Seconds between log checks
ANIMATION_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
MAX_LINE_LENGTH = 120  # Maximum length of displayed log lines
MAX_STORED_ENTRIES = 1000  # Limit on stored log entries

# ------------------------------
# Nord‑Themed Styles & Console Setup
# ------------------------------
console = Console()


def print_header(text: str) -> None:
    """Print a striking ASCII art header using pyfiglet."""
    ascii_art = pyfiglet.figlet_format(text, font="slant")
    console.print(ascii_art, style="bold #88C0D0")


def print_section(text: str) -> None:
    """Print a formatted section header."""
    console.print(f"\n[bold #88C0D0]{text}[/bold #88C0D0]")


def print_status(message: str, status_type: str = "info") -> None:
    """Print a status message with Nord‑themed colors."""
    colors = {
        "info": "#8FBCBB",
        "success": "#8FBCBB",
        "warning": "#EBCB8B",
        "error": "#BF616A",
        "critical": "#B48EAD",
    }
    color = colors.get(status_type.lower(), "#D8DEE9")
    console.print(message, style=color)


def print_error(message: str) -> None:
    """Print an error message."""
    print_status(message, "error")


def print_warning(message: str) -> None:
    """Print a warning message."""
    print_status(message, "warning")


def print_success(message: str) -> None:
    """Print a success message."""
    print_status(message, "success")


def truncate_line(line: str, max_length: int = MAX_LINE_LENGTH) -> str:
    """Truncate a line to the maximum length."""
    return line if len(line) <= max_length else line[: max_length - 3] + "..."


def format_timestamp(timestamp: Optional[float] = None) -> str:
    """Format a timestamp to a human-readable string."""
    if timestamp is None:
        timestamp = time.time()
    return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def check_root_privileges() -> None:
    """Warn the user if the script is not run with root privileges."""
    if os.geteuid() != 0:
        print_warning(
            "Running without root privileges. Some log files may be inaccessible."
        )


# ------------------------------
# Data Classes & Statistics
# ------------------------------
@dataclass
class LogPattern:
    """Represents a pattern to search for in log files."""

    name: str
    pattern: Pattern
    description: str
    severity: int


@dataclass
class LogMatch:
    """Represents a match of a pattern in a log file."""

    timestamp: float
    log_file: str
    pattern_name: str
    severity: int
    line: str


class LogStatistics:
    """Tracks statistics for log matches."""

    def __init__(self) -> None:
        self.total_lines: int = 0
        self.total_matches: int = 0
        self.pattern_matches: Dict[str, int] = defaultdict(int)
        self.file_matches: Dict[str, Dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        self.severity_counts: Dict[int, int] = defaultdict(int)
        self.start_time: float = time.time()
        self.lock = threading.Lock()

    def update(self, log_file: str, pattern_name: str, severity: int) -> None:
        with self.lock:
            self.total_matches += 1
            self.pattern_matches[pattern_name] += 1
            self.file_matches[log_file][pattern_name] += 1
            self.severity_counts[severity] += 1

    def increment_lines(self) -> None:
        with self.lock:
            self.total_lines += 1


# ------------------------------
# Core Log Monitor Class
# ------------------------------
class LogMonitor:
    """
    Monitors log files in real‑time for specified patterns. Supports
    custom pattern matching, summary reporting, and export of detected issues.
    """

    def __init__(
        self,
        log_files: List[str],
        pattern_configs: Dict[str, Dict[str, Any]] = None,
        max_stored_entries: int = MAX_STORED_ENTRIES,
    ) -> None:
        self.log_files = log_files
        self.max_stored_entries = max_stored_entries
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
        self.stop_event = threading.Event()
        self.matches_lock = threading.Lock()
        self.file_lock = threading.Lock()
        self.quiet_mode = False
        self.last_summary_time = 0
        self.animation_index = 0

    def _process_log_file(self, log_path: str) -> None:
        """Monitor a single log file for pattern matches."""
        try:
            if not os.path.exists(log_path):
                print_status(f"Log file not found: {log_path}", "warning")
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
            print_status(
                f"Permission denied: {log_path}. Try running as root.", "error"
            )
        except Exception as e:
            print_status(f"Error monitoring {log_path}: {str(e)}", "error")

    def _display_match(self, match: LogMatch) -> None:
        """Display a matched log line with appropriate formatting."""
        color = self._get_severity_color(match.severity)
        timestamp = format_timestamp(match.timestamp)
        filename = Path(match.log_file).name
        line = truncate_line(match.line)
        console.print(
            f"[dim]{timestamp}[/dim] [bold {color}][{match.pattern_name.upper()}][/bold {color}] "
            f"([italic]{filename}[/italic]): {line}"
        )

    def _get_severity_color(self, severity: int) -> str:
        """Return a Nord‑themed color based on severity level."""
        if severity == 1:
            return "#B48EAD"
        elif severity == 2:
            return "#BF616A"
        elif severity == 3:
            return "#EBCB8B"
        elif severity == 4:
            return "#8FBCBB"
        return "#D8DEE9"

    def _display_activity_indicator(self) -> None:
        """Display an animated indicator of monitoring activity."""
        self.animation_index = (self.animation_index + 1) % len(ANIMATION_FRAMES)
        indicator = ANIMATION_FRAMES[self.animation_index]
        sys.stdout.write(
            f"\r[dim]{indicator} Monitoring {len(self.log_files)} log file(s)... "
            f"({self.stats.total_matches} matches, {self.stats.total_lines} lines)[/dim]"
        )
        sys.stdout.flush()

    def _print_summary(self, force: bool = False) -> None:
        """Print a summary report of log statistics."""
        now = time.time()
        if not force and now - self.last_summary_time < SUMMARY_INTERVAL:
            return
        self.last_summary_time = now
        terminal_width = os.get_terminal_size().columns
        sys.stdout.write("\r" + " " * terminal_width + "\r")
        if not self.stats.total_matches and not force:
            return
        elapsed = now - self.stats.start_time
        elapsed_str = f"{int(elapsed // 3600)}h {int((elapsed % 3600) // 60)}m {int(elapsed % 60)}s"
        print_section("Log Monitor Summary")
        console.print(
            f"Monitoring Duration: [bold #D8DEE9]{elapsed_str}[/bold #D8DEE9]"
        )
        console.print(
            f"Total Lines Processed: [bold #D8DEE9]{self.stats.total_lines}[/bold #D8DEE9]"
        )
        console.print(
            f"Total Matches: [bold #D8DEE9]{self.stats.total_matches}[/bold #D8DEE9]"
        )
        if self.stats.severity_counts:
            console.print("\n[bold #88C0D0]Severity Breakdown:[/bold #88C0D0]")
            for severity in sorted(self.stats.severity_counts.keys()):
                count = self.stats.severity_counts[severity]
                color = self._get_severity_color(severity)
                severity_name = {
                    1: "Critical",
                    2: "Error",
                    3: "Warning",
                    4: "Notice",
                }.get(severity, f"Level {severity}")
                console.print(
                    f"  [bold {color}]{severity_name}: {count}[/bold {color}]"
                )
        if self.stats.pattern_matches:
            console.print("\n[bold #88C0D0]Pattern Matches:[/bold #88C0D0]")
            for pattern, count in sorted(
                self.stats.pattern_matches.items(), key=lambda x: x[1], reverse=True
            ):
                pattern_obj = self.patterns.get(pattern)
                if pattern_obj:
                    color = self._get_severity_color(pattern_obj.severity)
                    console.print(
                        f"  [bold {color}]{pattern.upper()}: {count}[/bold {color}]"
                    )
        if self.stats.file_matches:
            console.print("\n[bold #88C0D0]Log File Activity:[/bold #88C0D0]")
            for log_file, patterns in self.stats.file_matches.items():
                total = sum(patterns.values())
                filename = Path(log_file).name
                console.print(f"  [#D8DEE9]{filename}[/#D8DEE9]: {total} matches")
                for pattern, count in sorted(
                    patterns.items(), key=lambda x: x[1], reverse=True
                )[:3]:
                    pattern_obj = self.patterns.get(pattern)
                    if pattern_obj:
                        color = self._get_severity_color(pattern_obj.severity)
                        console.print(
                            f"    [bold {color}]{pattern.upper()}: {count}[/bold {color}]"
                        )
        console.print("\n")

    def export_results(self, export_format: str, output_file: str) -> bool:
        """
        Export collected log matches to a file in JSON or CSV format.
        """
        with self.matches_lock:
            matches_copy = list(self.matches)
        try:
            if export_format.lower() == "json":
                serializable = []
                for match in matches_copy:
                    serializable.append(
                        {
                            "timestamp": format_timestamp(match.timestamp),
                            "log_file": match.log_file,
                            "pattern_name": match.pattern_name,
                            "severity": match.severity,
                            "line": match.line,
                        }
                    )
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(serializable, f, indent=2)
            elif export_format.lower() == "csv":
                with open(output_file, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(
                        ["Timestamp", "Log File", "Pattern", "Severity", "Line"]
                    )
                    for match in matches_copy:
                        writer.writerow(
                            [
                                format_timestamp(match.timestamp),
                                match.log_file,
                                match.pattern_name,
                                match.severity,
                                match.line,
                            ]
                        )
            else:
                print_status(f"Unsupported export format: {export_format}", "error")
                return False
            print_status(
                f"Exported {len(matches_copy)} matches to {output_file}", "success"
            )
            return True
        except Exception as e:
            print_status(f"Export failed: {str(e)}", "error")
            return False

    def start_monitoring(self, quiet: bool = False, stats_only: bool = False) -> None:
        """Start monitoring all specified log files concurrently."""
        self.quiet_mode = quiet or stats_only
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        global SHUTDOWN_FLAG
        SHUTDOWN_FLAG = False

        print_header("Enhanced System Log Monitor")
        console.print(
            f"Starting log monitor at: [bold #D8DEE9]{format_timestamp()}[/bold #D8DEE9]"
        )
        console.print(
            f"Monitoring [bold #D8DEE9]{len(self.log_files)}[/bold #D8DEE9] log file(s)"
        )
        console.print(
            f"Tracking [bold #D8DEE9]{len(self.patterns)}[/bold #D8DEE9] pattern(s)"
        )
        console.print("Press Ctrl+C to stop monitoring\n", style="dim")

        for log_file in self.log_files:
            if os.path.exists(log_file):
                console.print(f"[bold #8FBCBB]✓ {log_file}[/bold #8FBCBB]")
            else:
                console.print(f"[bold #BF616A]✗ {log_file} (not found)[/bold #BF616A]")
        console.print("")

        threads = []
        for log_file in self.log_files:
            thread = threading.Thread(
                target=self._process_log_file, args=(log_file,), daemon=True
            )
            thread.start()
            threads.append(thread)

        try:
            while not SHUTDOWN_FLAG:
                if not stats_only:
                    self._display_activity_indicator()
                if not stats_only:
                    self._print_summary()
                time.sleep(0.5)
        except KeyboardInterrupt:
            SHUTDOWN_FLAG = True
        finally:
            self.stop_event.set()
            if self.stats.total_matches > 0 or stats_only:
                self._print_summary(force=True)
            print_status("\nLog monitoring completed", "success")
            for thread in threads:
                thread.join(timeout=0.5)


# ------------------------------
# Signal Handling & Cleanup
# ------------------------------
def signal_handler(sig: int, frame: Any) -> None:
    """Handle interrupt signals gracefully by setting the shutdown flag."""
    console.print(f"\n[bold #EBCB8B]Signal received, shutting down...[/bold #EBCB8B]")
    global SHUTDOWN_FLAG
    SHUTDOWN_FLAG = True


atexit.register(lambda: console.print("[dim]Cleaning up resources...[/dim]"))


# ------------------------------
# Main CLI Entry Point with Click
# ------------------------------
@click.command()
@click.argument("logs", nargs=-1)
@click.option(
    "-q", "--quiet", is_flag=True, help="Only show summaries, not individual matches"
)
@click.option(
    "-s",
    "--stats-only",
    is_flag=True,
    help="Only show final statistics when monitoring ends",
)
@click.option(
    "-i",
    "--interval",
    default=SUMMARY_INTERVAL,
    help="Interval in seconds between summary reports",
)
@click.option(
    "-p",
    "--patterns",
    type=click.Choice(["default", "network", "all"], case_sensitive=False),
    default="default",
    help="Pattern set to use for monitoring",
)
@click.option(
    "--custom-pattern",
    "custom_patterns",
    multiple=True,
    help="Add custom pattern in format 'name:regex:severity'",
)
@click.option(
    "-e",
    "--export",
    type=click.Choice(["json", "csv"], case_sensitive=False),
    help="Export results in the specified format when done",
)
@click.option(
    "-o",
    "--output",
    default="log_monitor_results",
    help="Output file name for export (without extension)",
)
def main(
    logs: List[str],
    quiet: bool,
    stats_only: bool,
    interval: int,
    patterns: str,
    custom_patterns: List[str],
    export: Optional[str],
    output: str,
) -> None:
    """Enhanced System Log Monitor"""
    global SUMMARY_INTERVAL
    SUMMARY_INTERVAL = interval
    print_header("System Log Monitor")
    console.print(f"Timestamp: [bold #D8DEE9]{format_timestamp()}[/bold #D8DEE9]")
    check_root_privileges()

    log_files = list(logs) if logs else DEFAULT_LOG_FILES
    if not log_files:
        print_status("No log files specified. Exiting.", "error")
        sys.exit(1)

    valid_logs = []
    for log_file in log_files:
        if (
            os.path.exists(log_file)
            and os.path.isfile(log_file)
            and os.access(log_file, os.R_OK)
        ):
            valid_logs.append(log_file)
        else:
            print_status(f"Invalid log file: {log_file}", "warning")
    if not valid_logs:
        print_status("Error: No valid log files to monitor. Exiting.", "error")
        sys.exit(1)

    pattern_set = DEFAULT_PATTERNS.copy()
    if patterns.lower() in ["network", "all"]:
        pattern_set.update(NETWORK_PATTERNS)
    if custom_patterns:
        for custom in custom_patterns:
            try:
                name, regex, severity = custom.split(":", 2)
                pattern_set[name] = {
                    "pattern": regex,
                    "description": f"Custom pattern: {name}",
                    "severity": int(severity),
                }
                print_status(f"Added custom pattern: {name}", "success")
            except ValueError:
                print_status(
                    f"Invalid custom pattern format: {custom}. Expected format: name:regex:severity",
                    "error",
                )

    monitor = LogMonitor(valid_logs, pattern_set)
    try:
        monitor.start_monitoring(quiet=quiet, stats_only=stats_only)
        if export and monitor.stats.total_matches > 0:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"{output}_{timestamp}.{export.lower()}"
            monitor.export_results(export, output_filename)
    except Exception as e:
        print_status(f"Unexpected error: {str(e)}", "error")
        sys.exit(1)


# Global shutdown flag
SHUTDOWN_FLAG = False

if __name__ == "__main__":
    main()
