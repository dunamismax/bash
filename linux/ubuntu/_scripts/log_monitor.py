#!/usr/bin/env python3
"""
Simplified System Log Monitor

Monitors system log files and reports on critical events.

Usage:
    python log_monitor.py [log files...]
"""

import argparse
import os
import re
import sys
import time
from collections import defaultdict
import threading


class LogMonitor:
    """
    A simple log monitoring class that tracks patterns in log files.
    """

    def __init__(self, log_files, patterns=None):
        """
        Initialize the log monitor.

        Args:
            log_files (list): Paths to log files to monitor
            patterns (dict, optional): Regex patterns to search for
        """
        self.log_files = log_files
        self.patterns = patterns or {
            "error": re.compile(r"\berror\b", re.IGNORECASE),
            "critical": re.compile(r"\bcritical\b", re.IGNORECASE),
            "warning": re.compile(r"\bwarning\b", re.IGNORECASE),
            "fail": re.compile(r"\bfail(?:ed|ure)?\b", re.IGNORECASE),
        }
        self.summary = defaultdict(lambda: defaultdict(int))
        self.stop_event = threading.Event()
        self.lock = threading.Lock()

    def _process_log_file(self, log_path):
        """
        Monitor a single log file for pattern matches.

        Args:
            log_path (str): Path to the log file
        """
        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                # Move to the end of the file
                f.seek(0, os.SEEK_END)

                print(f"Monitoring log file: {log_path}")

                while not self.stop_event.is_set():
                    line = f.readline()
                    if not line:
                        time.sleep(0.1)
                        continue

                    # Check for pattern matches
                    for pattern_name, regex in self.patterns.items():
                        if regex.search(line):
                            with self.lock:
                                # Update summary and print match
                                self.summary[log_path][pattern_name] += 1
                                print(
                                    f"[{pattern_name.upper()}] {log_path}: {line.strip()}"
                                )

        except FileNotFoundError:
            print(f"Error: Log file not found - {log_path}", file=sys.stderr)
        except Exception as e:
            print(f"Error monitoring {log_path}: {e}", file=sys.stderr)

    def start_monitoring(self):
        """
        Start monitoring all specified log files in separate threads.
        """
        threads = []
        for log_file in self.log_files:
            thread = threading.Thread(
                target=self._process_log_file, args=(log_file,), daemon=True
            )
            thread.start()
            threads.append(thread)

        # Print summary periodically
        try:
            while not self.stop_event.is_set():
                time.sleep(10)
                self._print_summary()
        except KeyboardInterrupt:
            print("\nMonitoring stopped by user.")
            self.stop_event.set()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

    def _print_summary(self):
        """
        Print a summary of pattern matches for all monitored log files.
        """
        with self.lock:
            if not any(self.summary.values()):
                return

            print("\n--- Log Monitor Summary ---")
            for log_path, patterns in self.summary.items():
                print(f"Log File: {log_path}")
                for pattern, count in patterns.items():
                    print(f"  {pattern.upper()}: {count}")
            print("---------------------------\n")


def main():
    """
    Main entry point for the log monitor.
    """
    parser = argparse.ArgumentParser(description="Simple System Log Monitor")
    parser.add_argument(
        "logs",
        nargs="*",
        default=["/var/log/syslog", "/var/log/auth.log"],
        help="Log files to monitor",
    )

    args = parser.parse_args()

    # Validate log files exist
    existing_logs = [log for log in args.logs if os.path.isfile(log)]

    if not existing_logs:
        print("Error: No valid log files specified.", file=sys.stderr)
        sys.exit(1)

    # Check for root privileges for system logs
    if os.geteuid() != 0:
        print("Warning: Some system logs may require root privileges.", file=sys.stderr)

    # Initialize and start log monitor
    monitor = LogMonitor(existing_logs)
    monitor.start_monitoring()


if __name__ == "__main__":
    main()
