#!/usr/bin/env python3
"""
Enhanced System Log Monitor
--------------------------------------------------

A fully automated terminal-based utility for monitoring system log files
in real-time with advanced pattern detection and visualization capabilities.

Features:
  • Monitors multiple log files concurrently (using default accessible logs)
  • Detects patterns (errors, warnings, critical issues, etc.) with regex
  • Displays a Nord-themed interface with dynamic ASCII headers, live updates,
    and progress spinners
  • Exports detected log matches automatically to a JSON file
  • Runs unattended for a predetermined duration

Version: 2.0.0
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

import shutil
import pyfiglet
from rich.align import Align
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.style import Style
from rich.table import Table
from rich.text import Text
from rich.traceback import install as install_rich_traceback

# Install rich traceback for better error reporting
install_rich_traceback(show_locals=True)


# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
APP_NAME: str = "Enhanced System Log Monitor"
APP_SUBTITLE: str = "Real-time Pattern Detection"
VERSION: str = "2.0.0"

# Default log files (only those accessible will be monitored)
DEFAULT_LOG_FILES: List[str] = [
    "/var/log/syslog",
    "/var/log/auth.log",
    "/var/log/kern.log",
    "/var/log/apache2/error.log",
    "/var/log/nginx/error.log",
]

# Default regex patterns for detecting log events
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

# Operation settings
SUMMARY_INTERVAL: int = 30  # Seconds between summary reports
UPDATE_INTERVAL: float = 0.1  # Seconds between log file checks
MAX_LINE_LENGTH: int = 120  # Maximum characters to display per log line
MAX_STORED_ENTRIES: int = 1000  # Maximum number of stored log matches
OPERATION_TIMEOUT: int = 30  # Seconds for operation timeouts

# Run monitoring for a fixed duration (in seconds)
MONITOR_DURATION: int = 60

# Terminal dimensions (constrained for a pleasant display)
TERM_WIDTH: int = min(shutil.get_terminal_size().columns, 100)
TERM_HEIGHT: int = min(shutil.get_terminal_size().lines, 30)

# Animation frames for progress indicators
ANIMATION_FRAMES: List[str] = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


# ----------------------------------------------------------------
# Nord-Themed Colors and Console Setup
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming throughout the application."""

    # Polar Night (dark) shades
    POLAR_NIGHT_1 = "#2E3440"
    POLAR_NIGHT_2 = "#3B4252"
    POLAR_NIGHT_3 = "#434C5E"
    POLAR_NIGHT_4 = "#4C566A"

    # Snow Storm (light) shades
    SNOW_STORM_1 = "#D8DEE9"
    SNOW_STORM_2 = "#E5E9F0"
    SNOW_STORM_3 = "#ECEFF4"

    # Frost (blues/cyans) shades
    FROST_1 = "#8FBCBB"
    FROST_2 = "#88C0D0"
    FROST_3 = "#81A1C1"
    FROST_4 = "#5E81AC"

    # Aurora (accent) shades
    RED = "#BF616A"  # errors
    ORANGE = "#D08770"  # warnings
    YELLOW = "#EBCB8B"  # caution
    GREEN = "#A3BE8C"  # success
    PURPLE = "#B48EAD"  # critical/special

    @staticmethod
    def get_severity_color(severity: int) -> str:
        """Return a color based on severity level (1=highest, 4=lowest)."""
        return {
            1: NordColors.PURPLE,
            2: NordColors.RED,
            3: NordColors.YELLOW,
            4: NordColors.FROST_1,
        }.get(severity, NordColors.SNOW_STORM_1)


console: Console = Console(theme=None, highlight=False)


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class LogPattern:
    """Represents a regex pattern for log monitoring."""

    name: str
    pattern: Pattern
    description: str
    severity: int


@dataclass
class LogMatch:
    """Represents a match of a log pattern in a monitored file."""

    timestamp: float
    log_file: str
    pattern_name: str
    severity: int
    line: str


class LogStatistics:
    """
    Thread-safe statistics container for tracking log processing.
    """

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

    def increment_lines(self) -> None:
        with self.lock:
            self.total_lines += 1

    def update(self, log_file: str, pattern_name: str, severity: int) -> None:
        with self.lock:
            self.total_matches += 1
            self.pattern_matches[pattern_name] += 1
            self.file_matches[log_file][pattern_name] += 1
            self.severity_counts[severity] += 1


# ----------------------------------------------------------------
# Console & Display Helpers
# ----------------------------------------------------------------
def create_header() -> Panel:
    """Generate an ASCII art header with a Nord-themed gradient."""
    try:
        fig = pyfiglet.Figlet(font="slant", width=TERM_WIDTH - 10)
        ascii_art = fig.renderText(APP_NAME)
    except Exception:
        fig = pyfiglet.Figlet(font="small", width=TERM_WIDTH - 10)
        ascii_art = fig.renderText(APP_NAME)

    ascii_lines = [line for line in ascii_art.split("\n") if line.strip()]
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
    tech_border = f"[{NordColors.FROST_3}]" + "━" * 40 + "[/]"
    styled_text = tech_border + "\n" + styled_text + tech_border

    return Panel(
        Text.from_markup(styled_text),
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
    )


def print_success(message: str) -> None:
    console.print(f"[bold {NordColors.GREEN}]✓ {message}[/]")


def print_warning(message: str) -> None:
    console.print(f"[bold {NordColors.YELLOW}]⚠ {message}[/]")


def print_error(message: str) -> None:
    console.print(f"[bold {NordColors.RED}]✗ {message}[/]")


def print_info(message: str) -> None:
    console.print(f"[{NordColors.FROST_3}]{message}[/]")


def print_section(title: str) -> None:
    border = "═" * min(len(title) + 10, TERM_WIDTH)
    console.print(f"\n[bold {NordColors.FROST_2}]{border}[/]")
    console.print(f"[bold {NordColors.FROST_2}]{title.center(len(border))}[/]")
    console.print(f"[bold {NordColors.FROST_2}]{border}[/]\n")


def clear_screen() -> None:
    console.clear()


def truncate_line(line: str, max_length: int = MAX_LINE_LENGTH) -> str:
    return line if len(line) <= max_length else line[: max_length - 3] + "..."


def format_timestamp(timestamp: Optional[float] = None) -> str:
    if timestamp is None:
        timestamp = time.time()
    return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def format_time(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f}m"
    else:
        return f"{seconds / 3600:.1f}h"


# ----------------------------------------------------------------
# System Helper Functions
# ----------------------------------------------------------------
def check_root_privileges() -> bool:
    return os.geteuid() == 0 if hasattr(os, "geteuid") else False


def warn_if_not_root() -> None:
    if not check_root_privileges():
        print_warning(
            "Running without root privileges – some log files may be inaccessible."
        )


# ----------------------------------------------------------------
# Signal Handling & Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    print_info("Performing cleanup tasks...")


def signal_handler(sig: int, frame: Any) -> None:
    sig_name = (
        signal.Signals(sig).name if hasattr(signal, "Signals") else f"signal {sig}"
    )
    print_warning(f"\nProcess interrupted by {sig_name}.")
    cleanup()
    sys.exit(128 + sig)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Progress Tracking Classes
# ----------------------------------------------------------------
class ProgressManager:
    """Unified progress tracking using Rich Progress."""

    def __init__(self):
        self.progress = Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_2}"),
            TextColumn("[bold {task.fields[color]}]{task.description}"),
            BarColumn(
                bar_width=None,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
            expand=True,
        )

    def __enter__(self):
        self.progress.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.progress.stop()

    def add_task(self, description: str, total: float, color: str = NordColors.FROST_2):
        return self.progress.add_task(
            description,
            total=total,
            color=color,
            status=f"{NordColors.FROST_3}starting",
        )

    def update(self, task_id, advance: float = 0, **kwargs) -> None:
        self.progress.update(task_id, advance=advance, **kwargs)


class Spinner:
    """A simple spinner for indeterminate progress."""

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
                    f"\r[{NordColors.FROST_3}]{self.spinner_chars[self.current]}[/] "
                    f"[{NordColors.FROST_2}]{self.message}[/] "
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
                console.print(
                    f"[{NordColors.GREEN}]✓[/] [{NordColors.FROST_2}]{self.message}[/] "
                    f"[{NordColors.GREEN}]completed[/] in {time_str}"
                )
            else:
                console.print(
                    f"[{NordColors.RED}]✗[/] [{NordColors.FROST_2}]{self.message}[/] "
                    f"[{NordColors.RED}]failed[/] after {time_str}"
                )

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop(success=exc_type is None)


# ----------------------------------------------------------------
# Core Log Monitor Class
# ----------------------------------------------------------------
class LogMonitor:
    """
    Monitors a list of log files for specified patterns in real time.
    Provides live summary reporting and export of matched log entries.
    """

    def __init__(
        self,
        log_files: List[str],
        pattern_configs: Dict[str, Dict[str, Any]],
        max_stored_entries: int = MAX_STORED_ENTRIES,
        summary_interval: int = SUMMARY_INTERVAL,
    ) -> None:
        self.log_files = log_files
        self.max_stored_entries = max_stored_entries
        self.summary_interval = summary_interval
        self.patterns: Dict[str, LogPattern] = {}
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
        self.shutdown_flag = False

    def _process_log_file(self, log_path: str) -> None:
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
        color = NordColors.get_severity_color(match.severity)
        timestamp = format_timestamp(match.timestamp)
        filename = Path(match.log_file).name
        line = truncate_line(match.line)
        console.print(
            f"[dim]{timestamp}[/dim] [bold {color}][{match.pattern_name.upper()}][/bold {color}] "
            f"([italic]{filename}[/italic]): {line}"
        )

    def _display_activity_indicator(self) -> None:
        # Simple live indicator (animation)
        indicator = ANIMATION_FRAMES[int(time.time() * 10) % len(ANIMATION_FRAMES)]
        console.print(
            f"\r[dim]{indicator} Monitoring {len(self.log_files)} log file(s)... "
            f"({self.stats.total_matches} matches, {self.stats.total_lines} lines)[/dim]",
            end="",
        )

    def _print_summary(self, force: bool = False) -> None:
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
        console.print(
            f"Monitoring Duration: [bold {NordColors.SNOW_STORM_1}]{elapsed_str}[/bold {NordColors.SNOW_STORM_1}]"
        )
        console.print(
            f"Total Lines Processed: [bold {NordColors.SNOW_STORM_1}]{self.stats.total_lines}[/bold {NordColors.SNOW_STORM_1}]"
        )
        console.print(
            f"Total Matches: [bold {NordColors.SNOW_STORM_1}]{self.stats.total_matches}[/bold {NordColors.SNOW_STORM_1}]"
        )
        if self.stats.severity_counts:
            console.print(
                f"\n[bold {NordColors.FROST_2}]Severity Breakdown:[/bold {NordColors.FROST_2}]"
            )
            for severity in sorted(self.stats.severity_counts.keys()):
                count = self.stats.severity_counts[severity]
                color = NordColors.get_severity_color(severity)
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
            console.print(
                f"\n[bold {NordColors.FROST_2}]Pattern Matches:[/bold {NordColors.FROST_2}]"
            )
            for pattern, count in sorted(
                self.stats.pattern_matches.items(), key=lambda x: x[1], reverse=True
            ):
                pattern_obj = self.patterns.get(pattern)
                if pattern_obj:
                    color = NordColors.get_severity_color(pattern_obj.severity)
                    console.print(
                        f"  [bold {color}]{pattern.upper()}: {count}[/bold {color}]"
                    )
        if self.stats.file_matches:
            console.print(
                f"\n[bold {NordColors.FROST_2}]Log File Activity:[/bold {NordColors.FROST_2}]"
            )
            for log_file, patterns in self.stats.file_matches.items():
                total = sum(patterns.values())
                filename = Path(log_file).name
                console.print(
                    f"  [{NordColors.SNOW_STORM_1}]{filename}[/{NordColors.SNOW_STORM_1}]: {total} matches"
                )
                for pattern, count in sorted(
                    patterns.items(), key=lambda x: x[1], reverse=True
                )[:3]:
                    pattern_obj = self.patterns.get(pattern)
                    if pattern_obj:
                        color = NordColors.get_severity_color(pattern_obj.severity)
                        console.print(
                            f"    [bold {color}]{pattern.upper()}: {count}[/bold {color}]"
                        )
        console.print("")

    def export_results(self, export_format: str, output_file: str) -> bool:
        with self.matches_lock:
            matches_copy = list(self.matches)
        if not matches_copy:
            print_warning("No matches to export.")
            return False
        try:
            if export_format.lower() == "json":
                serializable = [
                    {
                        "timestamp": format_timestamp(match.timestamp),
                        "log_file": match.log_file,
                        "pattern": match.pattern_name,
                        "severity": match.severity,
                        "line": match.line,
                    }
                    for match in matches_copy
                ]
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
                print_error(f"Unsupported export format: {export_format}")
                return False
            print_success(f"Exported {len(matches_copy)} matches to {output_file}")
            return True
        except Exception as e:
            print_error(f"Export failed: {e}")
            return False

    def start_monitoring(self, quiet: bool = False, stats_only: bool = False) -> None:
        self.quiet_mode = quiet or stats_only
        self.shutdown_flag = False
        clear_screen()
        console.print(create_header())
        print_info(f"Starting log monitor at: {format_timestamp()}")
        print_info(f"Monitoring {len(self.log_files)} log file(s)")
        print_info(f"Tracking {len(self.patterns)} pattern(s)")
        warn_if_not_root()
        for log_file in self.log_files:
            if os.path.exists(log_file) and os.access(log_file, os.R_OK):
                print_success(f"Monitoring: {log_file}")
            else:
                print_error(f"Cannot access: {log_file}")
        console.print("")
        threads = []
        for log_file in self.log_files:
            thread = threading.Thread(
                target=self._process_log_file, args=(log_file,), daemon=True
            )
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
        self.shutdown_flag = True
        self.stop_event.set()


# ----------------------------------------------------------------
# Main Automated Workflow
# ----------------------------------------------------------------
def main() -> None:
    try:
        clear_screen()
        console.print(create_header())
        print_info(f"Starting log monitoring at {format_timestamp()}")
        warn_if_not_root()

        # Automatically filter default logs to only those accessible
        available_logs = [
            lf
            for lf in DEFAULT_LOG_FILES
            if os.path.exists(lf) and os.access(lf, os.R_OK)
        ]
        if not available_logs:
            print_error("No accessible log files found. Exiting.")
            sys.exit(1)
        print_success(f"Monitoring {len(available_logs)} log file(s):")
        for lf in available_logs:
            print_info(f" - {lf}")

        # Merge built-in and network patterns
        pattern_configs = DEFAULT_PATTERNS.copy()
        pattern_configs.update(NETWORK_PATTERNS)

        # Create the log monitor instance
        log_monitor = LogMonitor(
            log_files=available_logs,
            pattern_configs=pattern_configs,
            max_stored_entries=MAX_STORED_ENTRIES,
            summary_interval=SUMMARY_INTERVAL,
        )

        print_info(f"Monitoring for {MONITOR_DURATION} seconds...")
        monitor_thread = threading.Thread(
            target=log_monitor.start_monitoring,
            kwargs={"quiet": False, "stats_only": False},
        )
        monitor_thread.start()
        time.sleep(MONITOR_DURATION)
        log_monitor.stop_monitoring()
        monitor_thread.join()

        log_monitor._print_summary(force=True)

        # Automatically export results to JSON
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"log_monitor_results_{timestamp}.json"
        print_info(f"Exporting results to {output_file}...")
        with Spinner("Exporting results"):
            success = log_monitor.export_results("json", output_file)
        if success:
            print_success("Export completed successfully.")
        else:
            print_error("Export failed.")
        print_success("Log monitoring completed.")
    except KeyboardInterrupt:
        print_warning("Monitoring interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
