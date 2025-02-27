#!/usr/bin/env python3
"""
Enhanced System Log Monitor

A comprehensive tool to monitor system log files in real-time, detecting and reporting
on important patterns such as errors, warnings, and critical messages. The monitor
provides color-coded output, detailed summaries, and custom pattern detection.

Features:
  • Real-time monitoring of multiple log files concurrently
  • Customizable pattern matching with severity levels
  • Color-coded output using Nord theme colors
  • Regular summary reports with statistics
  • Export capabilities for detected issues
  • Graceful handling of system signals

Usage:
  python log_monitor.py [options] [log files...]

Note: Some system logs may require root privileges to access.
"""

import argparse
import csv
import datetime
import json
import logging
import os
import re
import signal
import sys
import threading
import time
from collections import defaultdict, Counter
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import (
    Dict,
    List,
    Pattern,
    Set,
    Optional,
    Tuple,
    Callable,
    Any,
    Union,
    DefaultDict,
)

#####################################
# Configuration
#####################################

# Default log files to monitor if none specified
DEFAULT_LOG_FILES = [
    "/var/log/syslog",
    "/var/log/auth.log",
    "/var/log/kern.log",
    "/var/log/apache2/error.log",
    "/var/log/nginx/error.log",
]

# Default patterns to search for in log files
DEFAULT_PATTERNS = {
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

# Specific IP-based patterns
NETWORK_PATTERNS = {
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

# UI Configuration
SUMMARY_INTERVAL = 30  # Seconds between summary reports
UPDATE_INTERVAL = 0.1  # Seconds between log checks
ANIMATION_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
MAX_LINE_LENGTH = 120  # Maximum length of displayed log lines
MAX_STORED_ENTRIES = 1000  # Maximum number of log entries to store in memory

#####################################
# UI and Color Definitions (Nord Theme)
#####################################


class NordColors:
    """ANSI color codes using Nord color palette"""

    # Base colors
    RESET = "\033[0m"
    BOLD = "\033[1m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"

    # Nord theme foreground colors
    INFO = "\033[38;2;163;190;140m"  # Nord14 (green)
    SUCCESS = "\033[38;2;163;190;140m"  # Nord14 (green)
    WARNING = "\033[38;2;235;203;139m"  # Nord13 (yellow)
    ERROR = "\033[38;2;191;97;106m"  # Nord11 (red)
    CRITICAL = "\033[38;2;180;142;173m"  # Nord15 (purple)
    HEADER = "\033[38;2;129;161;193m"  # Nord9 (blue)
    NORMAL = "\033[38;2;216;222;233m"  # Nord4 (light gray)
    DETAIL = "\033[38;2;136;192;208m"  # Nord8 (light blue)
    MUTED = "\033[38;2;76;86;106m"  # Nord3 (dark gray)

    # Background colors
    BG_DARK = "\033[48;2;46;52;64m"  # Nord0 (dark)
    BG_ERROR = "\033[48;2;191;97;106m"  # Nord11 (red bg)


class SeverityColors:
    """Maps severity levels to Nord color codes"""

    @staticmethod
    def get_color(severity: int) -> str:
        """Get color code for a severity level"""
        if severity == 1:
            return NordColors.CRITICAL
        elif severity == 2:
            return NordColors.ERROR
        elif severity == 3:
            return NordColors.WARNING
        elif severity == 4:
            return NordColors.INFO
        else:
            return NordColors.NORMAL


#####################################
# Helper Functions
#####################################


def format_timestamp(timestamp: Optional[float] = None) -> str:
    """
    Format a timestamp in a human-readable format.

    Args:
        timestamp: Unix timestamp (or current time if None)

    Returns:
        Formatted timestamp string
    """
    if timestamp is None:
        timestamp = time.time()
    return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def truncate_line(line: str, max_length: int = MAX_LINE_LENGTH) -> str:
    """
    Truncate a line to the specified maximum length.

    Args:
        line: Line to truncate
        max_length: Maximum length

    Returns:
        Truncated line
    """
    if len(line) <= max_length:
        return line
    return line[: max_length - 3] + "..."


def print_header(message: str) -> None:
    """
    Print a formatted header message.

    Args:
        message: Message to display as header
    """
    terminal_width = os.get_terminal_size().columns
    print(f"\n{NordColors.HEADER}{NordColors.BOLD}{'═' * terminal_width}")
    print(f" {message}")
    print(f"{'═' * terminal_width}{NordColors.RESET}\n")


def print_section(message: str) -> None:
    """
    Print a formatted section header.

    Args:
        message: Section header message
    """
    print(f"\n{NordColors.DETAIL}{NordColors.BOLD}▶ {message}{NordColors.RESET}")


def print_status(message: str, status_type: str = "info") -> None:
    """
    Print a status message with appropriate coloring.

    Args:
        message: Status message to display
        status_type: Type of status (info, success, warning, error)
    """
    color = {
        "info": NordColors.INFO,
        "success": NordColors.SUCCESS,
        "warning": NordColors.WARNING,
        "error": NordColors.ERROR,
        "critical": NordColors.CRITICAL,
    }.get(status_type.lower(), NordColors.NORMAL)

    print(f"{color}{message}{NordColors.RESET}")


def signal_handler(sig: int, frame: Any) -> None:
    """
    Handle interrupt signals gracefully by setting the global shutdown flag.

    Args:
        sig: Signal number
        frame: Current stack frame
    """
    print(f"\n{NordColors.WARNING}Signal received, shutting down...{NordColors.RESET}")
    # The shutdown flag will be checked by the main loop
    global SHUTDOWN_FLAG
    SHUTDOWN_FLAG = True


#####################################
# Data Classes
#####################################


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
    """Tracks statistics for log patterns."""

    def __init__(self) -> None:
        """Initialize statistics counters."""
        self.total_lines: int = 0
        self.total_matches: int = 0
        self.pattern_matches: DefaultDict[str, int] = defaultdict(int)
        self.file_matches: DefaultDict[str, DefaultDict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        self.severity_counts: DefaultDict[int, int] = defaultdict(int)
        self.start_time: float = time.time()
        self.lock = threading.Lock()

    def update(self, log_file: str, pattern_name: str, severity: int) -> None:
        """
        Update statistics with a new match.

        Args:
            log_file: Path to the log file
            pattern_name: Name of the matched pattern
            severity: Severity level of the match
        """
        with self.lock:
            self.total_matches += 1
            self.pattern_matches[pattern_name] += 1
            self.file_matches[log_file][pattern_name] += 1
            self.severity_counts[severity] += 1

    def increment_lines(self) -> None:
        """Increment the total number of processed lines."""
        with self.lock:
            self.total_lines += 1


#####################################
# Core Monitor Classes
#####################################


class LogMonitor:
    """
    A comprehensive log monitoring system that tracks patterns in log files.
    """

    def __init__(
        self,
        log_files: List[str],
        pattern_configs: Dict[str, Dict[str, Any]] = None,
        max_stored_entries: int = MAX_STORED_ENTRIES,
    ) -> None:
        """
        Initialize the log monitor.

        Args:
            log_files: Paths to log files to monitor
            pattern_configs: Dictionary of pattern configurations
            max_stored_entries: Maximum number of log entries to store in memory
        """
        self.log_files = log_files
        self.max_stored_entries = max_stored_entries

        # Compile patterns from configurations
        self.patterns: Dict[str, LogPattern] = {}
        pattern_configs = pattern_configs or DEFAULT_PATTERNS

        for name, config in pattern_configs.items():
            self.patterns[name] = LogPattern(
                name=name,
                pattern=re.compile(config["pattern"], re.IGNORECASE),
                description=config["description"],
                severity=config["severity"],
            )

        # Initialize statistics and storage
        self.stats = LogStatistics()
        self.matches: List[LogMatch] = []
        self.file_positions: Dict[str, int] = {}

        # Thread control
        self.stop_event = threading.Event()
        self.matches_lock = threading.Lock()
        self.file_lock = threading.Lock()

        # Output control
        self.quiet_mode = False
        self.last_summary_time = 0
        self.animation_index = 0

    def _process_log_file(self, log_path: str) -> None:
        """
        Monitor a single log file for pattern matches.

        Args:
            log_path: Path to the log file
        """
        try:
            # Check if file exists before processing
            if not os.path.exists(log_path):
                print_status(f"Log file not found: {log_path}", "warning")
                return

            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                # Get file size and move to end if we haven't seen this file yet
                with self.file_lock:
                    if log_path not in self.file_positions:
                        self.file_positions[log_path] = os.path.getsize(log_path)
                    f.seek(self.file_positions[log_path])

                while not self.stop_event.is_set():
                    # Read from last position
                    lines = f.readlines()
                    if not lines:
                        # Update file position before waiting
                        with self.file_lock:
                            self.file_positions[log_path] = f.tell()
                        time.sleep(UPDATE_INTERVAL)
                        continue

                    for line in lines:
                        self.stats.increment_lines()
                        # Strip to remove trailing newlines
                        line = line.strip()

                        # Check all patterns for matches
                        for name, pattern_obj in self.patterns.items():
                            if pattern_obj.pattern.search(line):
                                timestamp = time.time()

                                # Create a log match object
                                match = LogMatch(
                                    timestamp=timestamp,
                                    log_file=log_path,
                                    pattern_name=name,
                                    severity=pattern_obj.severity,
                                    line=line,
                                )

                                # Update statistics
                                self.stats.update(log_path, name, pattern_obj.severity)

                                # Store the match
                                with self.matches_lock:
                                    self.matches.append(match)
                                    # Limit stored matches to control memory usage
                                    if len(self.matches) > self.max_stored_entries:
                                        self.matches.pop(0)

                                # Display the match unless in quiet mode
                                if not self.quiet_mode:
                                    self._display_match(match)

                    # Update file position
                    with self.file_lock:
                        self.file_positions[log_path] = f.tell()

        except PermissionError:
            print_status(
                f"Permission denied: {log_path}\nTry running as root for system logs.",
                "error",
            )
        except Exception as e:
            print_status(f"Error monitoring {log_path}: {str(e)}", "error")

    def _display_match(self, match: LogMatch) -> None:
        """
        Display a pattern match with appropriate formatting and colors.

        Args:
            match: The log match to display
        """
        # Get color based on severity
        color = SeverityColors.get_color(match.severity)

        # Format timestamp and file name
        timestamp = format_timestamp(match.timestamp)
        filename = os.path.basename(match.log_file)

        # Truncate line for display
        line = truncate_line(match.line)

        # Print with appropriate coloring
        print(
            f"{NordColors.MUTED}[{timestamp}]{NordColors.RESET} "
            f"{color}{NordColors.BOLD}[{match.pattern_name.upper()}]{NordColors.RESET} "
            f"{NordColors.DETAIL}({filename}){NordColors.RESET}: {line}"
        )

    def _display_activity_indicator(self) -> None:
        """Display an animated activity indicator."""
        self.animation_index = (self.animation_index + 1) % len(ANIMATION_FRAMES)
        sys.stdout.write(
            f"\r{NordColors.MUTED}{ANIMATION_FRAMES[self.animation_index]} "
            f"Monitoring {len(self.log_files)} log files... "
            f"({self.stats.total_matches} matches, {self.stats.total_lines} lines processed)"
            f"{NordColors.RESET}"
        )
        sys.stdout.flush()

    def _print_summary(self, force: bool = False) -> None:
        """
        Print a summary of pattern matches for all monitored log files.

        Args:
            force: Whether to force printing the summary even if interval hasn't elapsed
        """
        now = time.time()

        # Check if it's time for a summary
        if not force and now - self.last_summary_time < SUMMARY_INTERVAL:
            return

        self.last_summary_time = now

        # Clear the activity indicator line
        sys.stdout.write("\r" + " " * os.get_terminal_size().columns + "\r")

        # Skip if no matches and not forced
        if not self.stats.total_matches and not force:
            return

        # Calculate elapsed time
        elapsed = now - self.stats.start_time
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)
        elapsed_str = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"

        # Print the summary header
        print_section("Log Monitor Summary")
        print(f"{NordColors.NORMAL}Monitoring Duration: {elapsed_str}")
        print(f"Total Lines Processed: {self.stats.total_lines}")
        print(f"Total Matches: {self.stats.total_matches}{NordColors.RESET}")

        # Print severity counts
        if self.stats.severity_counts:
            print(f"\n{NordColors.DETAIL}Severity Breakdown:{NordColors.RESET}")
            for severity in sorted(self.stats.severity_counts.keys()):
                count = self.stats.severity_counts[severity]
                color = SeverityColors.get_color(severity)
                severity_name = {
                    1: "Critical",
                    2: "Error",
                    3: "Warning",
                    4: "Notice",
                }.get(severity, f"Level {severity}")
                print(f"  {color}{severity_name}: {count}{NordColors.RESET}")

        # Print pattern matches
        if self.stats.pattern_matches:
            print(f"\n{NordColors.DETAIL}Pattern Matches:{NordColors.RESET}")
            for pattern, count in sorted(
                self.stats.pattern_matches.items(), key=lambda x: x[1], reverse=True
            ):
                pattern_obj = self.patterns.get(pattern)
                if pattern_obj:
                    color = SeverityColors.get_color(pattern_obj.severity)
                    print(f"  {color}{pattern.upper()}: {count}{NordColors.RESET}")

        # Print file matches
        if self.stats.file_matches:
            print(f"\n{NordColors.DETAIL}Log File Activity:{NordColors.RESET}")
            for log_file, patterns in self.stats.file_matches.items():
                total = sum(patterns.values())
                filename = os.path.basename(log_file)
                print(
                    f"  {NordColors.NORMAL}{filename}: {total} matches{NordColors.RESET}"
                )

                # Show top 3 patterns for this file
                for pattern, count in sorted(
                    patterns.items(), key=lambda x: x[1], reverse=True
                )[:3]:
                    pattern_obj = self.patterns.get(pattern)
                    if pattern_obj:
                        color = SeverityColors.get_color(pattern_obj.severity)
                        print(
                            f"    {color}{pattern.upper()}: {count}{NordColors.RESET}"
                        )

        print("\n")  # Add extra line at the end

    def export_results(self, export_format: str, output_file: str) -> bool:
        """
        Export the collected results to a file.

        Args:
            export_format: Format to export (json or csv)
            output_file: Path to the output file

        Returns:
            True if export succeeded, False otherwise
        """
        with self.matches_lock:
            # Create a copy of matches for thread safety
            matches_copy = list(self.matches)

        try:
            if export_format.lower() == "json":
                # Convert to serializable format
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
        """
        Start monitoring all specified log files in separate threads.

        Args:
            quiet: Whether to suppress individual match output
            stats_only: Whether to only show statistics at the end
        """
        self.quiet_mode = quiet or stats_only

        # Register signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Set global shutdown flag
        global SHUTDOWN_FLAG
        SHUTDOWN_FLAG = False

        # Display starting information
        print_header("Enhanced System Log Monitor")
        print(f"{NordColors.NORMAL}Starting log monitor at: {format_timestamp()}")
        print(f"Monitoring {len(self.log_files)} log file(s)")
        print(f"Tracking {len(self.patterns)} pattern(s)")
        print(f"Press Ctrl+C to stop monitoring{NordColors.RESET}\n")

        # List monitoring files
        for log_file in self.log_files:
            if os.path.exists(log_file):
                print(f"{NordColors.SUCCESS}✓ {log_file}{NordColors.RESET}")
            else:
                print(f"{NordColors.ERROR}✗ {log_file} (not found){NordColors.RESET}")

        print("")  # Add extra line

        # Start a thread for each log file
        threads = []
        for log_file in self.log_files:
            thread = threading.Thread(
                target=self._process_log_file, args=(log_file,), daemon=True
            )
            thread.start()
            threads.append(thread)

        # Main monitoring loop
        try:
            while not SHUTDOWN_FLAG:
                if not stats_only:
                    self._display_activity_indicator()

                # Print summary at regular intervals if not in stats-only mode
                if not stats_only:
                    self._print_summary()

                time.sleep(0.5)

        except KeyboardInterrupt:
            SHUTDOWN_FLAG = True

        finally:
            # Set stop event for all threads
            self.stop_event.set()

            # Show final summary if matches were found or in stats_only mode
            if self.stats.total_matches > 0 or stats_only:
                self._print_summary(force=True)

            print_status("\nLog monitoring completed", "success")

            # Wait for threads to finish
            for thread in threads:
                thread.join(timeout=0.5)


#####################################
# Validation Functions
#####################################


def check_root_privileges() -> None:
    """Check if script is run with root privileges and warn if not."""
    if os.geteuid() != 0:
        print_status(
            "Warning: Some system logs may require root privileges.", "warning"
        )
        print_status(
            "Consider running with 'sudo' for full access to system logs.", "warning"
        )


def validate_log_files(log_files: List[str]) -> List[str]:
    """
    Validate that log files exist and are readable.

    Args:
        log_files: List of log file paths to validate

    Returns:
        List of valid log files
    """
    valid_logs = []

    for log_file in log_files:
        if not os.path.exists(log_file):
            print_status(f"Log file not found: {log_file}", "warning")
            continue

        if not os.path.isfile(log_file):
            print_status(f"Not a file: {log_file}", "warning")
            continue

        if not os.access(log_file, os.R_OK):
            print_status(f"No read permission: {log_file}", "warning")
            continue

        valid_logs.append(log_file)

    return valid_logs


#####################################
# Main Function
#####################################


def main() -> None:
    """Main entry point for the log monitor."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Enhanced System Log Monitor",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Log file selection
    parser.add_argument(
        "logs",
        nargs="*",
        help="Log files to monitor (uses system logs if none specified)",
    )

    # Display options
    display_group = parser.add_argument_group("Display Options")
    display_group.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Only show summaries, not individual matches",
    )
    display_group.add_argument(
        "-s",
        "--stats-only",
        action="store_true",
        help="Only show final statistics when monitoring ends",
    )
    display_group.add_argument(
        "-i",
        "--interval",
        type=int,
        default=SUMMARY_INTERVAL,
        help="Interval in seconds between summary reports",
    )

    # Pattern options
    pattern_group = parser.add_argument_group("Pattern Options")
    pattern_group.add_argument(
        "-p",
        "--patterns",
        choices=["default", "network", "all"],
        default="default",
        help="Pattern set to use for monitoring",
    )
    pattern_group.add_argument(
        "--custom-pattern",
        action="append",
        dest="custom_patterns",
        help="Add custom pattern in format 'name:regex:severity'",
    )

    # Export options
    export_group = parser.add_argument_group("Export Options")
    export_group.add_argument(
        "-e",
        "--export",
        choices=["json", "csv"],
        help="Export results in the specified format when done",
    )
    export_group.add_argument(
        "-o",
        "--output",
        default="log_monitor_results",
        help="Output file name for export (without extension)",
    )

    args = parser.parse_args()

    # Update summary interval from arguments
    global SUMMARY_INTERVAL
    SUMMARY_INTERVAL = args.interval

    # Check privilege level
    check_root_privileges()

    # Determine log files to monitor
    log_files = args.logs
    if not log_files:
        # Use default logs
        log_files = DEFAULT_LOG_FILES
        print_status("No log files specified, using system defaults", "info")

    # Validate log files
    valid_logs = validate_log_files(log_files)

    if not valid_logs:
        print_status("Error: No valid log files to monitor. Exiting.", "error")
        sys.exit(1)

    # Select pattern set
    patterns = DEFAULT_PATTERNS.copy()
    if args.patterns == "network" or args.patterns == "all":
        patterns.update(NETWORK_PATTERNS)

    # Add custom patterns if provided
    if args.custom_patterns:
        for custom in args.custom_patterns:
            try:
                name, regex, severity = custom.split(":", 2)
                patterns[name] = {
                    "pattern": regex,
                    "description": f"Custom pattern: {name}",
                    "severity": int(severity),
                }
                print_status(f"Added custom pattern: {name}", "success")
            except ValueError:
                print_status(
                    f"Invalid custom pattern format: {custom}\n"
                    f"Expected format: name:regex:severity",
                    "error",
                )

    # Initialize and start log monitor
    monitor = LogMonitor(valid_logs, patterns)

    try:
        # Start monitoring
        monitor.start_monitoring(quiet=args.quiet, stats_only=args.stats_only)

        # Export results if requested
        if args.export and monitor.stats.total_matches > 0:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"{args.output}_{timestamp}.{args.export}"
            monitor.export_results(args.export, output_filename)

    except Exception as e:
        print_status(f"Unexpected error: {str(e)}", "error")
        sys.exit(1)


# Global shutdown flag
SHUTDOWN_FLAG = False

if __name__ == "__main__":
    main()
