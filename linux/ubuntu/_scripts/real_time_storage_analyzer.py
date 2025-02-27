#!/usr/bin/env python3
"""
Advanced Real-Time Storage & Network Monitoring System
------------------------------------------------------
Description:
  A comprehensive, high-performance CLI application for monitoring:
  - Local disk partitions (ext4, XFS, BTRFS, ZFS)
  - Network-attached storage (NFS, CIFS)
  - ZFS pools
  - Network interfaces
  - System resources

  Features:
  - Real-time metrics with minimal system overhead
  - Rich, colorful terminal interface
  - Detailed error handling and logging
  - Modular architecture
  - Performance-optimized data collection

Usage:
  python3 storage_analyzer.py [options]

Author: Your Name | License: MIT | Version: 3.0.0
"""

# Standard library imports
import argparse
import concurrent.futures
import logging
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Union

# Third-party imports
import psutil
import netifaces
# Removed ifaddr import as it's not necessary
from rich import box
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

# ------------------------------------------------------------------------------
# Configuration and Logging
# ------------------------------------------------------------------------------
class ConfigManager:
    """Centralized configuration management."""
    
    @dataclass
    class Settings:
        """Application settings with sensible defaults."""
        refresh_rate: float = 1.0
        log_level: str = 'INFO'
        color_theme: str = 'nord'
        network_interfaces: List[str] = field(default_factory=list)
        include_network_storage: bool = True
        debug_mode: bool = False

    _instance = None
    _settings = Settings()

    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_settings(cls):
        return cls._settings

    @classmethod
    def update_settings(cls, **kwargs):
        for key, value in kwargs.items():
            if hasattr(cls._settings, key):
                setattr(cls._settings, key, value)

# Logging Configuration
def setup_logging(log_level: str = 'INFO') -> logging.Logger:
    """
    Configure logging with enhanced flexibility.
    
    Args:
        log_level: Logging level as string
    
    Returns:
        Configured logger instance
    """
    # Determine log file path
    log_dir = os.path.expanduser('~/.local/log')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'storage_analyzer.log')

    # Convert log level string to logging constant
    log_level = getattr(logging, log_level.upper(), logging.INFO)

    # Configure logger
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s | %(levelname)8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.StreamHandler(sys.stderr),
            logging.FileHandler(log_file, mode='a', encoding='utf-8')
        ]
    )

    logger = logging.getLogger(__name__)
    return logger

# Global logger
logger = setup_logging()

# ------------------------------------------------------------------------------
# Utility Functions
# ------------------------------------------------------------------------------
def safe_run(func, *args, default=None, log_error=True):
    """
    Safely execute a function with error handling.
    
    Args:
        func: Function to execute
        *args: Arguments for the function
        default: Default return value if function fails
        log_error: Whether to log errors
    
    Returns:
        Function result or default value
    """
    try:
        return func(*args)
    except Exception as e:
        if log_error:
            logger.error(f"Error in {func.__name__}: {e}", exc_info=True)
        return default

# Size and formatting utilities
def format_size(size_bytes: Union[int, float], precision: int = 2) -> str:
    """
    Convert bytes to human-readable format with improved performance.
    
    Args:
        size_bytes: Size in bytes
        precision: Number of decimal places
    
    Returns:
        Formatted size string
    """
    if size_bytes == 0:
        return "0 B"
    
    # Use binary prefixes (1024-based)
    units = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB']
    unit_index = 0
    
    while size_bytes >= 1024 and unit_index < len(units) - 1:
        size_bytes /= 1024
        unit_index += 1
    
    return f"{size_bytes:.{precision}f} {units[unit_index]}"

# ------------------------------------------------------------------------------
# Collectors: Specialized Data Collection Classes
# ------------------------------------------------------------------------------
class BaseCollector:
    """Base class for data collectors with common interface and error handling."""
    
    def collect(self):
        """
        Abstract method to collect data.
        
        Raises:
            NotImplementedError: If not implemented by subclass
        """
        raise NotImplementedError("Subclasses must implement collect method")

class DiskCollector(BaseCollector):
    """Collect comprehensive disk and partition information."""
    
    @staticmethod
    def collect():
        """
        Collect detailed disk and partition metrics.
        
        Returns:
            List of disk metrics dictionaries
        """
        try:
            disks = []
            partitions = psutil.disk_partitions(all=False)
            io_counters = psutil.disk_io_counters(perdisk=True)
            
            for part in partitions:
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    base_device = part.device.rstrip('0123456789')
                    
                    # Get IO stats
                    io = io_counters.get(base_device, io_counters.get(part.device))
                    read_bytes = io.read_bytes if io else 0
                    write_bytes = io.write_bytes if io else 0
                    
                    disk_info = {
                        'device': part.device,
                        'mountpoint': part.mountpoint,
                        'filesystem': part.fstype,
                        'total': usage.total,
                        'used': usage.used,
                        'free': usage.free,
                        'percent': usage.percent,
                        'read_bytes': read_bytes,
                        'write_bytes': write_bytes
                    }
                    disks.append(disk_info)
                
                except Exception as partition_error:
                    logger.warning(f"Error processing partition {part.device}: {partition_error}")
            
            return disks
        
        except Exception as e:
            logger.error(f"Disk collection error: {e}")
            return []

class NetworkCollector(BaseCollector):
    """Collect network interface and storage information."""
    
    @staticmethod
    def get_ip_address(interface):
        """
        Get IP address for a given network interface.
        
        Args:
            interface: Network interface name
        
        Returns:
            IPv4 address or 'N/A'
        """
        try:
            # Try using socket
            ip = socket.gethostbyname(socket.gethostname())
            return ip
        except Exception:
            try:
                # Fallback to netifaces
                addrs = netifaces.ifaddresses(interface)
                ipv4 = addrs.get(netifaces.AF_INET, [{}])[0].get('addr', 'N/A')
                return ipv4
            except Exception:
                return 'N/A'
    
    @staticmethod
    def collect():
        """
        Collect network interface metrics and network storage info.
        
        Returns:
            Dict with network interface and storage information
        """
        network_info = {
            'interfaces': [],
            'network_storage': []
        }
        
        # Collect network interfaces
        try:
            # Use psutil for network IO stats
            net_io_counters = psutil.net_io_counters(pernic=True)
            
            # Collect interfaces
            for iface in netifaces.interfaces():
                try:
                    # Skip loopback and inactive interfaces
                    if iface == 'lo' or not net_io_counters.get(iface):
                        continue
                    
                    # Get IP and network stats
                    stats = net_io_counters.get(iface)
                    ipv4 = NetworkCollector.get_ip_address(iface)
                    
                    interface_info = {
                        'name': iface,
                        'ipv4': ipv4,
                        'bytes_sent': stats.bytes_sent,
                        'bytes_recv': stats.bytes_recv
                    }
                    network_info['interfaces'].append(interface_info)
                
                except Exception as iface_error:
                    logger.warning(f"Error processing interface {iface}: {iface_error}")
            
            # Detect network storage (basic implementation)
            network_storage_mounts = [
                mount for mount in psutil.disk_partitions() 
                if mount.fstype in ['nfs', 'cifs', 'smbfs']
            ]
            
            for mount in network_storage_mounts:
                try:
                    usage = psutil.disk_usage(mount.mountpoint)
                    network_info['network_storage'].append({
                        'mount': mount.mountpoint,
                        'type': mount.fstype,
                        'total': usage.total,
                        'used': usage.used,
                        'free': usage.free
                    })
                except Exception as storage_error:
                    logger.warning(f"Error processing network storage {mount.mountpoint}: {storage_error}")
        
        except Exception as e:
            logger.error(f"Network collection error: {e}")
        
        return network_info

class ZFSCollector(BaseCollector):
    """Collect ZFS pool information."""
    
    @staticmethod
    def collect():
        """
        Collect ZFS pool metrics using zpool command.
        
        Returns:
            List of ZFS pool dictionaries
        """
        pools = []
        try:
            # Use subprocess for zpool command with timeout
            result = subprocess.run(
                ['zpool', 'list', '-H', '-o', 'name,size,alloc,free,capacity,health'], 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            
            for line in result.stdout.strip().splitlines():
                try:
                    name, size, alloc, free, capacity, health = line.split()
                    pools.append({
                        'name': name,
                        'size': size,
                        'allocated': alloc,
                        'free': free,
                        'capacity': capacity,
                        'health': health
                    })
                except Exception as pool_parse_error:
                    logger.warning(f"Error parsing ZFS pool: {pool_parse_error}")
        
        except subprocess.TimeoutExpired:
            logger.error("ZFS pool collection timed out")
        except FileNotFoundError:
            logger.info("ZFS not installed or not in PATH")
        except Exception as e:
            logger.error(f"ZFS collection error: {e}")
        
        return pools

# ------------------------------------------------------------------------------
# Visualization Renderer
# ------------------------------------------------------------------------------
class TerminalRenderer:
    """Advanced terminal visualization using Rich."""
    
    @staticmethod
    def render_disk_table(disks):
        """Create Rich table for disk information."""
        table = Table(title="Disk Partitions", expand=True)
        
        # Add columns one by one
        table.add_column("Device", style="bold", justify="center")
        table.add_column("Mount", style="dim", justify="center")
        table.add_column("FS", justify="center")
        table.add_column("Total", justify="right")
        table.add_column("Used", justify="right")
        table.add_column("Free", justify="right")
        table.add_column("Usage %", justify="right")
        table.add_column("Read/s", justify="right")
        table.add_column("Write/s", justify="right")
        
        for disk in disks:
            table.add_row(
                disk['device'], 
                disk['mountpoint'], 
                disk['filesystem'],
                format_size(disk['total']),
                format_size(disk['used']),
                format_size(disk['free']),
                f"{disk['percent']}%",
                format_size(disk.get('read_bytes', 0)) + "/s",
                format_size(disk.get('write_bytes', 0)) + "/s"
            )
        
        return table

    @staticmethod
    def render_network_table(network_data):
        """Create Rich table for network interfaces."""
        table = Table(title="Network Interfaces", expand=True)
        table.add_column("Interface", justify="center")
        table.add_column("IPv4", justify="center")
        table.add_column("Sent", justify="right")
        table.add_column("Received", justify="right")
        
        for iface in network_data.get('interfaces', []):
            table.add_row(
                iface['name'], 
                iface['ipv4'], 
                format_size(iface['bytes_sent']),
                format_size(iface['bytes_recv'])
            )
        
        return table

    @staticmethod
    def render_zfs_table(pools):
        """Create Rich table for ZFS pools."""
        table = Table(title="ZFS Pools", expand=True)
        table.add_column("Pool", justify="center")
        table.add_column("Size", justify="right")
        table.add_column("Allocated", justify="right")
        table.add_column("Free", justify="right")
        table.add_column("Capacity", justify="right")
        table.add_column("Health", justify="center")
        
        for pool in pools:
            table.add_row(
                pool['name'], 
                pool['size'], 
                pool['allocated'], 
                pool['free'], 
                pool['capacity'], 
                pool['health']
            )
        
        return table

# ------------------------------------------------------------------------------
# Main Application
# ------------------------------------------------------------------------------
class StorageAnalyzer:
    """
    Main application class for comprehensive system storage monitoring.
    """
    
    def __init__(self, config=None):
        """
        Initialize the storage analyzer.
        
        Args:
            config: Optional configuration dictionary
        """
        self.config = config or ConfigManager.get_settings()
        self.console = Console()
    
    def run(self):
        """
        Main monitoring loop with Rich Live display.
        """
        logger.info("Starting Advanced Storage Analyzer")
        
        try:
            with Live(console=self.console, refresh_per_second=4, transient=True) as live:
                while True:
                    # Parallel data collection
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        disk_future = executor.submit(DiskCollector.collect)
                        network_future = executor.submit(NetworkCollector.collect)
                        zfs_future = executor.submit(ZFSCollector.collect)
                        
                        # Wait for all collectors to complete
                        disks = disk_future.result()
                        network_data = network_future.result()
                        zfs_pools = zfs_future.result()
                    
                    # Render tables
                    layout = Layout()
                    layout.split_column(
                        Layout(name="disks"),
                        Layout(name="network"),
                        Layout(name="zfs")
                    )
                    
                    # Update layout with rendered tables
                    layout['disks'].update(
                        Panel(
                            self.render_disk_table(disks), 
                            title="Disk Partitions", 
                            border_style="blue"
                        )
                    )
                    layout['network'].update(
                        Panel(
                            self.render_network_table(network_data), 
                            title="Network Interfaces", 
                            border_style="green"
                        )
                    )
                    layout['zfs'].update(
                        Panel(
                            self.render_zfs_table(zfs_pools), 
                            title="ZFS Pools", 
                            border_style="magenta"
                        )
                    )
                    
                    live.update(layout)
                    time.sleep(self.config.refresh_rate)
        
        except KeyboardInterrupt:
            logger.info("Storage analyzer stopped by user.")
        except Exception as e:
            logger.error(f"Unhandled error in storage analyzer: {e}", exc_info=True)
    
    def render_disk_table(self, disks):
        """Proxy method for disk table rendering."""
        return TerminalRenderer.render_disk_table(disks)
    
    def render_network_table(self, network_data):
        """Proxy method for network table rendering."""
        return TerminalRenderer.render_network_table(network_data)
    
    def render_zfs_table(self, zfs_pools):
        """Proxy method for ZFS table rendering."""
        return TerminalRenderer.render_zfs_table(zfs_pools)

# ------------------------------------------------------------------------------
# CLI Argument Parsing
# ------------------------------------------------------------------------------
def parse_arguments():
    """
    Parse command-line arguments for the storage analyzer.
    
    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="Advanced Real-Time Storage & Network Monitoring System",
        epilog="Monitor system storage, network interfaces, and ZFS pools in real-time."
    )
    
    parser.add_argument(
        '-r', '--refresh-rate', 
        type=float, 
        default=1.0, 
        help='Refresh interval in seconds (default: 1.0)'
    )
    
    parser.add_argument(
        '-l', '--log-level', 
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        default='INFO',
        help='Set the logging level (default: INFO)'
    )
    
    parser.add_argument(
        '-d', '--debug', 
        action='store_true',
        help='Enable debug mode with additional logging'
    )
    
    parser.add_argument(
        '--no-network', 
        action='store_true',
        help='Disable network interface monitoring'
    )
    
    parser.add_argument(
        '--no-zfs', 
        action='store_true',
        help='Disable ZFS pool monitoring'
    )
    
    parser.add_argument(
        '-i', '--interface', 
        action='append',
        help='Specify network interfaces to monitor (can be used multiple times)'
    )
    
    return parser.parse_args()

def main():
    """
    Main entry point for the storage analyzer application.
    Handles configuration, initialization, and running the analyzer.
    """
    # Parse command-line arguments
    args = parse_arguments()
    
    # Update configuration based on arguments
    config_settings = {
        'refresh_rate': args.refresh_rate,
        'log_level': args.log_level,
        'debug_mode': args.debug,
        'include_network_storage': not args.no_network,
        'network_interfaces': args.interface or []
    }
    
    # Update global configuration
    ConfigManager.update_settings(**config_settings)
    
    # Reconfigure logging based on CLI arguments
    global logger
    logger = setup_logging(args.log_level)
    
    # Handle debug mode
    if args.debug:
        logger.setLevel(logging.DEBUG)
        logger.debug("Debug mode enabled")
    
    # Initialize and run the storage analyzer
    try:
        analyzer = StorageAnalyzer()
        analyzer.run()
    except Exception as e:
        logger.error(f"Unhandled error in storage analyzer: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
