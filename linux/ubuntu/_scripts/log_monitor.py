#!/usr/bin/env python3
"""
Enhanced System Log Monitor
---------------------------------------------------------

A fully automated terminal-based utility for monitoring system log files
with advanced pattern detection and visualization capabilities. This tool
uses asynchronous processing to efficiently monitor multiple log sources
in real-time.

Features:
  • Monitors system logs and application logs (Caddy, Plex, Nextcloud)
  • Uses async I/O for efficient concurrent log processing
  • Detects patterns (errors, warnings, critical issues) with regex
  • Nord-themed interface with dynamic ASCII headers and live updates
  • Exports detected log matches to JSON or CSV
  • Displays real-time statistics and summary reports
  • Runs unattended or in interactive mode

Version: 3.0.0
"""

import asyncio
import atexit
import csv
import datetime
import json
import os
import re
import signal
import sys
import shutil
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Pattern,
    Set,
    Tuple,
    DefaultDict,
    Deque,
    Union,
    Callable,
    TypeVar,
    cast,
)

try:
    import pyfiglet
    from rich import box
    from rich.align import Align
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import (
        Progress,
        SpinnerColumn,
        BarColumn,
        TextColumn,
        TaskProgressColumn,
        TimeRemainingColumn,
    )
    from rich.prompt import Prompt, Confirm
    from rich.style import Style
    from rich.table import Table
    from rich.text import Text
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print(
        "Required libraries not found. Please install them using:\n"
        "pip install rich pyfiglet"
    )
    sys.exit(1)

# Install rich traceback for better error reporting
install_rich_traceback(show_locals=True)

# ----------------------------------------------------------------
# Configuration & Constants
# ----------------------------------------------------------------
APP_NAME: str = "Enhanced System Log Monitor"
APP_SUBTITLE: str = "Real-time Pattern Detection"
VERSION: str = "3.0.0"

# Default system log files (only accessible ones will be monitored)
SYSTEM_LOG_FILES: List[str] = [
    "/var/log/syslog",
    "/var/log/auth.log",
    "/var/log/kern.log",
    "/var/log/daemon.log",
    "/var/log/dpkg.log",
]

# Common web server logs
WEB_LOG_FILES: List[str] = [
    "/var/log/apache2/error.log",
    "/var/log/apache2/access.log",
    "/var/log/nginx/error.log",
    "/var/log/nginx/access.log",
]

# Caddy server logs
CADDY_LOG_FILES: List[str] = [
    "/var/log/caddy/access.log",
    "/var/log/caddy/error.log",
    "/var/lib/caddy/.local/share/caddy/logs/access.log",
]

# Plex Media Server logs
PLEX_LOG_FILES: List[str] = [
    "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Logs/Plex Media Server.log",
    "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Logs/Plex Transcoder.log",
    "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Logs/Plex DLNA Server.log",
]

# Nextcloud logs
NEXTCLOUD_LOG_FILES: List[str] = [
    "/var/www/nextcloud/data/nextcloud.log",
    "/var/log/nextcloud/nextcloud.log",
]

# Combine all log files
ALL_LOG_FILES: List[str] = (
    SYSTEM_LOG_FILES
    + WEB_LOG_FILES
    + CADDY_LOG_FILES
    + PLEX_LOG_FILES
    + NEXTCLOUD_LOG_FILES
)

# Configuration file paths
CONFIG_DIR: str = os.path.expanduser("~/.config/log_monitor")
CONFIG_FILE: str = os.path.join(CONFIG_DIR, "config.json")

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

# Security-related patterns
SECURITY_PATTERNS: Dict[str, Dict[str, Any]] = {
    "auth_failure": {
        "pattern": r"Failed password|authentication failure|Invalid user",
        "description": "Authentication failures",
        "severity": 2,
    },
    "access_denied": {
        "pattern": r"(access denied|permission denied)",
        "description": "Permission issues for resources",
        "severity": 3,
    },
    "sudo_usage": {
        "pattern": r"sudo:.*(COMMAND|USER)",
        "description": "Use of sudo privileges",
        "severity": 3,
    },
    "exploit_attempt": {
        "pattern": r"(exploit|injection|attack|overflow|CVE-\d{4}-\d+)",
        "description": "Possible exploitation attempts",
        "severity": 1,
    },
}

# Caddy-specific patterns
CADDY_PATTERNS: Dict[str, Dict[str, Any]] = {
    "caddy_error": {
        "pattern": r"(level=error|level=fatal|Error:)",
        "description": "Caddy server errors",
        "severity": 2,
    },
    "caddy_cert": {
        "pattern": r"(tls.obtain|certificate|ACME|obtaining|renewing)",
        "description": "Caddy certificate events",
        "severity": 3,
    },
    "caddy_http_error": {
        "pattern": r"(status=4\d\d|status=5\d\d)",
        "description": "HTTP client/server errors",
        "severity": 3,
    },
}

# Plex-specific patterns
PLEX_PATTERNS: Dict[str, Dict[str, Any]] = {
    "plex_error": {
        "pattern": r"(Error|ERROR|Exception|Failed)",
        "description": "Plex Media Server errors",
        "severity": 2,
    },
    "plex_transcode": {
        "pattern": r"(Transcoder|transcoding|transcode session)",
        "description": "Plex transcoding events",
        "severity": 4,
    },
    "plex_stream": {
        "pattern": r"(Stream|streaming|Direct Play|Direct Stream)",
        "description": "Plex streaming events",
        "severity": 4,
    },
}

# Nextcloud-specific patterns
NEXTCLOUD_PATTERNS: Dict[str, Dict[str, Any]] = {
    "nextcloud_error": {
        "pattern": r"(\{\"level\":3|\{\"level\":4|\[error\])",
        "description": "Nextcloud errors",
        "severity": 2,
    },
    "nextcloud_warning": {
        "pattern": r"(\{\"level\":2|\[warning\])",
        "description": "Nextcloud warnings",
        "severity": 3,
    },
    "nextcloud_login": {
        "pattern": r"(Login|Successful login|Failed login)",
        "description": "Nextcloud login events",
        "severity": 3,
    },
    "nextcloud_file": {
        "pattern": r"(upload|download|share|file_)",
        "description": "Nextcloud file operations",
        "severity": 4,
    },
}

# Merge all patterns
ALL_PATTERNS: Dict[str, Dict[str, Any]] = {
    **DEFAULT_PATTERNS,
    **SECURITY_PATTERNS,
    **CADDY_PATTERNS,
    **PLEX_PATTERNS,
    **NEXTCLOUD_PATTERNS,
}

# Operation settings
SUMMARY_INTERVAL: int = 30  # Seconds between summary reports
UPDATE_INTERVAL: float = 0.1  # Seconds between log file checks
MAX_LINE_LENGTH: int = 120  # Maximum characters to display per log line
MAX_STORED_ENTRIES: int = 2000  # Maximum number of stored log matches
OPERATION_TIMEOUT: int = 30  # Seconds for operation timeouts
AUTO_REFRESH_INTERVAL: int = 300  # Auto-refresh interval (5 minutes)

# Default monitoring duration (0 for continuous monitoring)
DEFAULT_MONITOR_DURATION: int = 0

# Animation frames for progress indicators
ANIMATION_FRAMES: List[str] = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    """Nord color palette for consistent theming throughout the application."""

    # Polar Night (dark) shades
    POLAR_NIGHT_1: str = "#2E3440"
    POLAR_NIGHT_2: str = "#3B4252"
    POLAR_NIGHT_3: str = "#434C5E"
    POLAR_NIGHT_4: str = "#4C566A"

    # Snow Storm (light) shades
    SNOW_STORM_1: str = "#D8DEE9"
    SNOW_STORM_2: str = "#E5E9F0"
    SNOW_STORM_3: str = "#ECEFF4"

    # Frost (blues/cyans) shades
    FROST_1: str = "#8FBCBB"
    FROST_2: str = "#88C0D0"
    FROST_3: str = "#81A1C1"
    FROST_4: str = "#5E81AC"

    # Aurora (accent) shades
    RED: str = "#BF616A"  # errors
    ORANGE: str = "#D08770"  # warnings
    YELLOW: str = "#EBCB8B"  # caution
    GREEN: str = "#A3BE8C"  # success
    PURPLE: str = "#B48EAD"  # critical/special

    @classmethod
    def get_frost_gradient(cls, steps: int = 4) -> List[str]:
        """Return a gradient using Frost colors."""
        frosts = [cls.FROST_1, cls.FROST_2, cls.FROST_3, cls.FROST_4]
        return frosts[:steps]

    @staticmethod
    def get_severity_color(severity: int) -> str:
        """Return a color based on severity level (1=highest, 4=lowest)."""
        return {
            1: NordColors.PURPLE,
            2: NordColors.RED,
            3: NordColors.YELLOW,
            4: NordColors.FROST_1,
        }.get(severity, NordColors.SNOW_STORM_1)

    @staticmethod
    def get_category_color(category: str) -> str:
        """Return a color based on log category."""
        category_colors = {
            "system": NordColors.FROST_4,
            "security": NordColors.RED,
            "web": NordColors.FROST_2,
            "caddy": NordColors.GREEN,
            "plex": NordColors.PURPLE,
            "nextcloud": NordColors.FROST_1,
        }
        return category_colors.get(category.lower(), NordColors.SNOW_STORM_1)


# Initialize console
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
    category: str = "system"  # system, security, web, caddy, plex, nextcloud


@dataclass
class LogMatch:
    """Represents a match of a log pattern in a monitored file."""

    timestamp: float
    log_file: str
    pattern_name: str
    severity: int
    line: str
    category: str = "system"


@dataclass
class LogFile:
    """Represents a log file being monitored."""

    path: str
    name: str = ""
    category: str = "system"
    enabled: bool = True
    position: int = 0
    last_check: float = field(default_factory=time.time)
    lines_processed: int = 0
    matches_found: int = 0

    def __post_init__(self) -> None:
        """Initialize name from path if not provided."""
        if not self.name:
            self.name = Path(self.path).name


@dataclass
class AppConfig:
    """Application configuration settings."""

    log_files: List[LogFile] = field(default_factory=list)
    patterns: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    summary_interval: int = SUMMARY_INTERVAL
    update_interval: float = UPDATE_INTERVAL
    max_line_length: int = MAX_LINE_LENGTH
    max_stored_entries: int = MAX_STORED_ENTRIES
    auto_refresh_interval: int = AUTO_REFRESH_INTERVAL
    dark_mode: bool = True
    last_refresh: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Convert the config to a dictionary for serialization."""
        result = asdict(self)
        # Convert LogFile objects to dictionaries
        result["log_files"] = [asdict(lf) for lf in self.log_files]
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        """Create an AppConfig instance from a dictionary."""
        if "log_files" in data and isinstance(data["log_files"], list):
            data["log_files"] = [LogFile(**lf) for lf in data["log_files"]]
        return cls(**data)


class LogStatistics:
    """Thread-safe statistics container for tracking log processing."""

    def __init__(self) -> None:
        self.total_lines: int = 0
        self.total_matches: int = 0
        self.pattern_matches: DefaultDict[str, int] = defaultdict(int)
        self.file_matches: DefaultDict[str, DefaultDict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        self.category_matches: DefaultDict[str, int] = defaultdict(int)
        self.severity_counts: DefaultDict[int, int] = defaultdict(int)
        self.start_time: float = time.time()
        self.last_update: float = time.time()
        self.lock = asyncio.Lock()

    async def increment_lines(self, count: int = 1) -> None:
        """Increment the total lines processed."""
        async with self.lock:
            self.total_lines += count
            self.last_update = time.time()

    async def update(
        self, log_file: str, pattern_name: str, severity: int, category: str
    ) -> None:
        """Update statistics with a new match."""
        async with self.lock:
            self.total_matches += 1
            self.pattern_matches[pattern_name] += 1
            self.file_matches[log_file][pattern_name] += 1
            self.severity_counts[severity] += 1
            self.category_matches[category] += 1
            self.last_update = time.time()


# ----------------------------------------------------------------
# Console & Display Helpers
# ----------------------------------------------------------------
def create_header() -> Panel:
    """Generate an ASCII art header with a Nord-themed gradient."""
    term_width, _ = shutil.get_terminal_size((80, 24))
    try:
        font_to_use = "slant"
        if term_width < 60:
            font_to_use = "small"
        elif term_width < 40:
            font_to_use = "mini"

        fig = pyfiglet.Figlet(font=font_to_use, width=min(term_width - 10, 120))
        ascii_art = fig.renderText(APP_NAME)
    except Exception:
        ascii_art = f"  {APP_NAME}  "

    ascii_lines = [line for line in ascii_art.splitlines() if line.strip()]
    colors = NordColors.get_frost_gradient(len(ascii_lines))

    combined_text = Text()
    for i, line in enumerate(ascii_lines):
        color = colors[i % len(colors)]
        combined_text.append(Text(line, style=f"bold {color}"))
        if i < len(ascii_lines) - 1:
            combined_text.append("\n")

    return Panel(
        combined_text,
        border_style=Style(color=NordColors.FROST_1),
        padding=(1, 2),
        title=f"[bold {NordColors.SNOW_STORM_2}]v{VERSION}[/]",
        title_align="right",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{APP_SUBTITLE}[/]",
        subtitle_align="center",
        box=box.ROUNDED,
    )


def print_message(
    text: str, style: str = NordColors.FROST_2, prefix: str = "•"
) -> None:
    """Print a styled message with a prefix."""
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_success(message: str) -> None:
    """Print a success message."""
    print_message(message, NordColors.GREEN, "✓")


def print_warning(message: str) -> None:
    """Print a warning message."""
    print_message(message, NordColors.YELLOW, "⚠")


def print_error(message: str) -> None:
    """Print an error message."""
    print_message(message, NordColors.RED, "✗")


def print_info(message: str) -> None:
    """Print an informational message."""
    print_message(message, NordColors.FROST_3, "ℹ")


def print_section(title: str) -> None:
    """Print a section header."""
    console.print()
    console.print(f"[bold {NordColors.FROST_2}]{title}[/]")
    console.print(f"[{NordColors.FROST_2}]{'─' * len(title)}[/]")


def display_panel(title: str, message: str, style: str = NordColors.FROST_2) -> None:
    """Display a styled panel with a title and message."""
    panel = Panel(
        message,
        title=title,
        border_style=style,
        padding=(1, 2),
        box=box.ROUNDED,
    )
    console.print(panel)


def clear_screen() -> None:
    """Clear the terminal screen."""
    console.clear()


def truncate_line(line: str, max_length: int = MAX_LINE_LENGTH) -> str:
    """Truncate a line to a maximum length."""
    return line if len(line) <= max_length else line[: max_length - 3] + "..."


def format_timestamp(timestamp: Optional[float] = None) -> str:
    """Format a timestamp as a human-readable date and time."""
    if timestamp is None:
        timestamp = time.time()
    return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def format_time(seconds: float) -> str:
    """Format a time duration in a human-readable format."""
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
    """Check if the script is running with root privileges."""
    return os.geteuid() == 0 if hasattr(os, "geteuid") else False


def warn_if_not_root() -> None:
    """Warn if not running with root privileges."""
    if not check_root_privileges():
        print_warning(
            "Running without root privileges – some log files may be inaccessible."
        )


def ensure_config_directory() -> None:
    """Create config directory if it doesn't exist."""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
    except Exception as e:
        print_error(f"Could not create config directory: {e}")


def save_config(config: AppConfig) -> bool:
    """Save config to disk."""
    ensure_config_directory()
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config.to_dict(), f, indent=2)
        return True
    except Exception as e:
        print_error(f"Failed to save configuration: {e}")
        return False


def load_config() -> AppConfig:
    """Load config from disk or create default."""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
            return AppConfig.from_dict(data)
    except Exception as e:
        print_error(f"Failed to load configuration: {e}")

    # Create default config
    config = AppConfig(
        patterns=ALL_PATTERNS,
        summary_interval=SUMMARY_INTERVAL,
        update_interval=UPDATE_INTERVAL,
        max_line_length=MAX_LINE_LENGTH,
        max_stored_entries=MAX_STORED_ENTRIES,
        auto_refresh_interval=AUTO_REFRESH_INTERVAL,
    )

    # Initialize with accessible log files
    available_logs = []
    for log_path in ALL_LOG_FILES:
        category = "system"
        if any(log_path.startswith(p) for p in ["/var/log/apache", "/var/log/nginx"]):
            category = "web"
        elif any(log_path.startswith(p) for p in ["/var/log/caddy", "/var/lib/caddy"]):
            category = "caddy"
        elif "plexmediaserver" in log_path.lower():
            category = "plex"
        elif "nextcloud" in log_path.lower():
            category = "nextcloud"

        if os.path.exists(log_path) and os.access(log_path, os.R_OK):
            available_logs.append(
                LogFile(
                    path=log_path,
                    name=Path(log_path).name,
                    category=category,
                    enabled=True,
                )
            )

    config.log_files = available_logs
    save_config(config)
    return config


# ----------------------------------------------------------------
# Signal Handling & Cleanup
# ----------------------------------------------------------------
class CleanupManager:
    """Manager for cleanup tasks and signal handling."""

    def __init__(self) -> None:
        self.tasks: List[Callable[[], None]] = []
        self.setup_handlers()

    def add_task(self, task: Callable[[], None]) -> None:
        """Add a cleanup task."""
        self.tasks.append(task)

    def setup_handlers(self) -> None:
        """Set up signal handlers and atexit."""
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        atexit.register(self.cleanup)

    def cleanup(self) -> None:
        """Run all cleanup tasks."""
        print_info("Performing cleanup tasks...")
        for task in self.tasks:
            try:
                task()
            except Exception as e:
                print_error(f"Error during cleanup: {e}")

    def signal_handler(self, sig: int, frame: Any) -> None:
        """Handle signals and exit cleanly."""
        try:
            sig_name = (
                signal.Signals(sig).name
                if hasattr(signal, "Signals")
                else f"signal {sig}"
            )
            print_warning(f"\nProcess interrupted by {sig_name}.")
        except Exception:
            print_warning(f"\nProcess interrupted by signal {sig}.")

        self.cleanup()
        sys.exit(128 + sig)


# Global cleanup manager
cleanup_manager = CleanupManager()


# ----------------------------------------------------------------
# Progress Tracking Classes
# ----------------------------------------------------------------
class ProgressManager:
    """Unified progress tracking using Rich Progress."""

    def __init__(self) -> None:
        self.progress = Progress(
            SpinnerColumn(style=f"bold {NordColors.FROST_2}"),
            TextColumn("[bold {task.fields[color]}]{task.description}"),
            BarColumn(
                bar_width=None,
                style=NordColors.FROST_4,
                complete_style=NordColors.FROST_2,
            ),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
            expand=True,
        )

    def __enter__(self) -> "ProgressManager":
        self.progress.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.progress.stop()

    def add_task(
        self, description: str, total: float, color: str = NordColors.FROST_2
    ) -> int:
        """Add a task to the progress manager."""
        return self.progress.add_task(
            description,
            total=total,
            color=color,
        )

    def update(self, task_id: int, advance: float = 0, **kwargs: Any) -> None:
        """Update a task's progress."""
        self.progress.update(task_id, advance=advance, **kwargs)


class Spinner:
    """A simple spinner for indeterminate progress."""

    def __init__(self, message: str) -> None:
        self.message = message
        self.spinner_chars = ANIMATION_FRAMES
        self.current = 0
        self.spinning = False
        self.start_time = 0
        self._task: Optional[asyncio.Task] = None

    async def _spin(self) -> None:
        """Run the spinner animation."""
        while self.spinning:
            elapsed = time.time() - self.start_time
            time_str = format_time(elapsed)
            console.print(
                f"\r[{NordColors.FROST_3}]{self.spinner_chars[self.current]}[/] "
                f"[{NordColors.FROST_2}]{self.message}[/] "
                f"[[dim]elapsed: {time_str}[/dim]]",
                end="",
            )
            self.current = (self.current + 1) % len(self.spinner_chars)
            await asyncio.sleep(0.1)

    def start(self) -> None:
        """Start the spinner."""
        self.spinning = True
        self.start_time = time.time()
        self._task = asyncio.create_task(self._spin())

    async def stop(self, success: bool = True) -> None:
        """Stop the spinner."""
        self.spinning = False
        if self._task:
            await self._task
        elapsed = time.time() - self.start_time
        time_str = format_time(elapsed)
        console.print("\r" + " " * shutil.get_terminal_size().columns, end="\r")
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

    async def __aenter__(self) -> "Spinner":
        self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.stop(success=exc_type is None)


# ----------------------------------------------------------------
# Core Log Monitor Class
# ----------------------------------------------------------------
class LogMonitor:
    """
    Monitors multiple log files for specified patterns in real-time.
    Uses asyncio for concurrent processing and provides live updates.
    """

    def __init__(
        self,
        config: AppConfig,
    ) -> None:
        """Initialize the LogMonitor with configuration settings."""
        self.config = config
        self.log_files = {lf.path: lf for lf in config.log_files if lf.enabled}
        self.patterns: Dict[str, LogPattern] = {}

        # Compile all regex patterns
        for name, pattern_config in config.patterns.items():
            # Determine category from pattern name
            category = "system"
            if name in SECURITY_PATTERNS:
                category = "security"
            elif name in CADDY_PATTERNS:
                category = "caddy"
            elif name in PLEX_PATTERNS:
                category = "plex"
            elif name in NEXTCLOUD_PATTERNS:
                category = "nextcloud"

            self.patterns[name] = LogPattern(
                name=name,
                pattern=re.compile(pattern_config["pattern"], re.IGNORECASE),
                description=pattern_config["description"],
                severity=pattern_config["severity"],
                category=category,
            )

        self.stats = LogStatistics()
        self.matches: Deque[LogMatch] = deque(maxlen=config.max_stored_entries)
        self.stop_event = asyncio.Event()
        self.quiet_mode = False
        self.last_summary_time = 0
        self.file_watchers: Dict[str, asyncio.Task] = {}

    async def process_log_file(self, log_file: LogFile) -> None:
        """Process a single log file asynchronously."""
        try:
            if not os.path.exists(log_file.path):
                print_warning(f"Log file not found: {log_file.path}")
                return

            with open(log_file.path, "r", encoding="utf-8", errors="ignore") as f:
                # Set initial position
                if log_file.position > 0:
                    f.seek(log_file.position)
                else:
                    # Start at the end for new monitoring sessions
                    f.seek(0, os.SEEK_END)
                    log_file.position = f.tell()

                while not self.stop_event.is_set():
                    lines = f.readlines()
                    if not lines:
                        log_file.position = f.tell()
                        log_file.last_check = time.time()
                        await asyncio.sleep(self.config.update_interval)
                        continue

                    await self.stats.increment_lines(len(lines))
                    log_file.lines_processed += len(lines)

                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue

                        for name, pattern_obj in self.patterns.items():
                            if pattern_obj.pattern.search(line):
                                timestamp = time.time()
                                match = LogMatch(
                                    timestamp=timestamp,
                                    log_file=log_file.path,
                                    pattern_name=name,
                                    severity=pattern_obj.severity,
                                    line=line,
                                    category=pattern_obj.category,
                                )

                                await self.stats.update(
                                    log_file.path,
                                    name,
                                    pattern_obj.severity,
                                    pattern_obj.category,
                                )

                                log_file.matches_found += 1
                                self.matches.append(match)

                                if not self.quiet_mode:
                                    await self.display_match(match)

                    log_file.position = f.tell()
                    log_file.last_check = time.time()

        except PermissionError:
            print_error(f"Permission denied: {log_file.path}. Try running as root.")
        except Exception as e:
            print_error(f"Error monitoring {log_file.path}: {e}")

    async def display_match(self, match: LogMatch) -> None:
        """Display a log match in the console."""
        color = NordColors.get_severity_color(match.severity)
        timestamp = format_timestamp(match.timestamp)
        filename = Path(match.log_file).name
        line = truncate_line(match.line, self.config.max_line_length)

        category_color = NordColors.get_category_color(match.category)
        category_text = f"[{category_color}]{match.category.upper()}[/{category_color}]"

        console.print(
            f"[dim]{timestamp}[/dim] [bold {color}][{match.pattern_name.upper()}][/bold {color}] "
            f"{category_text} ([italic]{filename}[/italic]): {line}"
        )

    async def display_activity_indicator(self) -> None:
        """Display a simple live activity indicator."""
        if self.quiet_mode:
            return

        indicator = ANIMATION_FRAMES[int(time.time() * 10) % len(ANIMATION_FRAMES)]
        files_count = len(self.log_files)
        matches_count = self.stats.total_matches
        lines_count = self.stats.total_lines

        console.print(
            f"\r[dim]{indicator} Monitoring {files_count} log file(s)... "
            f"({matches_count} matches, {lines_count} lines)[/dim]",
            end="",
        )

    def create_summary_table(self) -> Table:
        """Create a table with monitoring statistics."""
        table = Table(
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
            box=box.ROUNDED,
            title="Log Monitoring Summary",
            expand=True,
        )

        table.add_column("Category", style=f"bold {NordColors.FROST_2}")
        table.add_column("Count", justify="right", style=f"{NordColors.SNOW_STORM_1}")
        table.add_column("Details", style=f"{NordColors.SNOW_STORM_2}")

        # Add rows for each category
        sorted_categories = sorted(
            self.stats.category_matches.items(), key=lambda x: x[1], reverse=True
        )

        for category, count in sorted_categories:
            color = NordColors.get_category_color(category)
            # Get details for this category (top patterns)
            category_patterns = []
            for pattern, pattern_count in self.stats.pattern_matches.items():
                pattern_obj = self.patterns.get(pattern)
                if pattern_obj and pattern_obj.category == category:
                    category_patterns.append((pattern, pattern_count))

            details = ", ".join(
                [
                    f"{p.upper()}: {c}"
                    for p, c in sorted(
                        category_patterns, key=lambda x: x[1], reverse=True
                    )[:3]
                ]
            )

            table.add_row(
                f"[bold {color}]{category.upper()}[/bold {color}]",
                str(count),
                details or "No pattern details",
            )

        return table

    def create_severity_table(self) -> Table:
        """Create a table showing severity distribution."""
        table = Table(
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
            box=box.ROUNDED,
            title="Severity Distribution",
        )

        table.add_column("Level", style=f"bold {NordColors.FROST_2}")
        table.add_column("Count", justify="right", style=f"{NordColors.SNOW_STORM_1}")
        table.add_column("Percentage", justify="right", style=f"{NordColors.FROST_3}")

        total = sum(self.stats.severity_counts.values())
        if total == 0:
            return table

        for severity in sorted(self.stats.severity_counts.keys()):
            count = self.stats.severity_counts[severity]
            percentage = (count / total) * 100
            color = NordColors.get_severity_color(severity)
            severity_name = {
                1: "Critical",
                2: "Error",
                3: "Warning",
                4: "Notice",
            }.get(severity, f"Level {severity}")

            table.add_row(
                f"[bold {color}]{severity_name}[/bold {color}]",
                str(count),
                f"{percentage:.1f}%",
            )

        return table

    def create_log_files_table(self) -> Table:
        """Create a table showing log file activity."""
        table = Table(
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
            box=box.ROUNDED,
            title="Log File Activity",
        )

        table.add_column("Log File", style=f"bold {NordColors.FROST_2}")
        table.add_column("Category", style=f"{NordColors.FROST_3}")
        table.add_column("Lines", justify="right", style=f"{NordColors.SNOW_STORM_1}")
        table.add_column("Matches", justify="right", style=f"{NordColors.SNOW_STORM_1}")

        # Sort log files by match count
        sorted_logs = sorted(
            self.log_files.values(), key=lambda lf: lf.matches_found, reverse=True
        )

        for log_file in sorted_logs:
            if log_file.lines_processed == 0 and log_file.matches_found == 0:
                continue

            category_color = NordColors.get_category_color(log_file.category)
            table.add_row(
                log_file.name,
                f"[{category_color}]{log_file.category}[/{category_color}]",
                str(log_file.lines_processed),
                str(log_file.matches_found),
            )

        return table

    async def display_summary(self, force: bool = False) -> None:
        """Display a summary of monitoring results."""
        now = time.time()
        if not force and now - self.last_summary_time < self.config.summary_interval:
            return

        self.last_summary_time = now
        if self.quiet_mode and not force:
            return

        console.print("\r" + " " * shutil.get_terminal_size().columns, end="\r")
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

        if self.stats.total_matches > 0:
            console.print()
            console.print(self.create_summary_table())
            console.print()
            console.print(self.create_severity_table())
            console.print()
            console.print(self.create_log_files_table())

        console.print()

    async def export_results(self, export_format: str, output_file: str) -> bool:
        """Export log matches to a file."""
        if not self.matches:
            print_warning("No matches to export.")
            return False

        try:
            matches_copy = list(self.matches)
            if export_format.lower() == "json":
                serializable = [
                    {
                        "timestamp": format_timestamp(match.timestamp),
                        "log_file": match.log_file,
                        "pattern": match.pattern_name,
                        "severity": match.severity,
                        "category": match.category,
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
                        [
                            "Timestamp",
                            "Log File",
                            "Pattern",
                            "Severity",
                            "Category",
                            "Line",
                        ]
                    )
                    for match in matches_copy:
                        writer.writerow(
                            [
                                format_timestamp(match.timestamp),
                                match.log_file,
                                match.pattern_name,
                                match.severity,
                                match.category,
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

    async def start_monitoring(
        self, quiet: bool = False, stats_only: bool = False, duration: int = 0
    ) -> None:
        """Start monitoring all log files."""
        self.quiet_mode = quiet or stats_only
        self.stop_event.clear()

        clear_screen()
        console.print(create_header())
        print_info(f"Starting log monitor at: {format_timestamp()}")

        enabled_logs = [lf for lf in self.log_files.values() if lf.enabled]
        print_info(f"Monitoring {len(enabled_logs)} log file(s)")
        print_info(f"Tracking {len(self.patterns)} pattern(s)")

        warn_if_not_root()

        # Check log file accessibility
        accessible_logs = 0
        for log_file in enabled_logs:
            if os.path.exists(log_file.path) and os.access(log_file.path, os.R_OK):
                print_success(f"Monitoring: {log_file.path}")
                accessible_logs += 1
            else:
                print_error(f"Cannot access: {log_file.path}")

        if accessible_logs == 0:
            print_error("No accessible log files found. Exiting.")
            return

        console.print("")

        # Start monitoring each log file
        for log_file in enabled_logs:
            if os.path.exists(log_file.path) and os.access(log_file.path, os.R_OK):
                task = asyncio.create_task(self.process_log_file(log_file))
                self.file_watchers[log_file.path] = task

        # Set up end time if duration specified
        end_time = time.time() + duration if duration > 0 else None

        try:
            while not self.stop_event.is_set():
                if end_time and time.time() >= end_time:
                    break

                if not stats_only:
                    await self.display_activity_indicator()

                await self.display_summary()
                await asyncio.sleep(0.5)

        except asyncio.CancelledError:
            print_warning("Monitoring tasks cancelled.")
        finally:
            await self.stop_monitoring()

            if self.stats.total_matches > 0 or stats_only:
                await self.display_summary(force=True)

            print_success("Log monitoring completed")

    async def stop_monitoring(self) -> None:
        """Stop all monitoring tasks."""
        self.stop_event.set()

        # Cancel all file watcher tasks
        for path, task in self.file_watchers.items():
            if not task.done():
                task.cancel()

        # Wait for all tasks to complete
        if self.file_watchers:
            await asyncio.gather(*self.file_watchers.values(), return_exceptions=True)

        self.file_watchers.clear()

        # Update config with current positions
        for log_file in self.log_files.values():
            for config_log_file in self.config.log_files:
                if config_log_file.path == log_file.path:
                    config_log_file.position = log_file.position
                    break

        # Save config
        save_config(self.config)


# ----------------------------------------------------------------
# CLI Interface
# ----------------------------------------------------------------
async def run_monitoring(
    duration: int = DEFAULT_MONITOR_DURATION,
    export_format: Optional[str] = None,
    quiet: bool = False,
    stats_only: bool = False,
) -> None:
    """Run the monitoring process for a specific duration."""
    config = load_config()
    log_monitor = LogMonitor(config)

    # Register cleanup task
    cleanup_manager.add_task(
        lambda: asyncio.run_coroutine_threadsafe(
            log_monitor.stop_monitoring(), asyncio.get_event_loop()
        )
    )

    try:
        await log_monitor.start_monitoring(
            quiet=quiet, stats_only=stats_only, duration=duration
        )

        # Export results if requested
        if export_format and export_format.lower() in ["json", "csv"]:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"log_monitor_results_{timestamp}.{export_format.lower()}"

            async with Spinner(f"Exporting results to {output_file}"):
                success = await log_monitor.export_results(export_format, output_file)

            if success:
                print_success("Export completed successfully.")
            else:
                print_error("Export failed.")

    except KeyboardInterrupt:
        print_warning("Monitoring interrupted by user.")
    except Exception as e:
        print_error(f"Unexpected error during monitoring: {e}")
        console.print_exception()


# ----------------------------------------------------------------
# Main Function
# ----------------------------------------------------------------
async def main() -> None:
    """Main entry point for the application."""
    try:
        parser = argparse.ArgumentParser(
            description=f"Enhanced System Log Monitor v{VERSION}"
        )
        parser.add_argument(
            "-d",
            "--duration",
            type=int,
            default=DEFAULT_MONITOR_DURATION,
            help="Duration to monitor in seconds (0 for continuous)",
        )
        parser.add_argument(
            "-e", "--export", choices=["json", "csv"], help="Export format for results"
        )
        parser.add_argument(
            "-q",
            "--quiet",
            action="store_true",
            help="Quiet mode (show only summaries)",
        )
        parser.add_argument(
            "-s",
            "--stats-only",
            action="store_true",
            help="Stats only mode (show only final statistics)",
        )

        args = parser.parse_args()

        await run_monitoring(
            duration=args.duration,
            export_format=args.export,
            quiet=args.quiet,
            stats_only=args.stats_only,
        )

    except KeyboardInterrupt:
        print_warning("Application interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    import argparse

    asyncio.run(main())
