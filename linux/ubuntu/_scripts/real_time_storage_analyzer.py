#!/usr/bin/env python3
"""
Simple System Resource Monitor

Monitors system storage and network interfaces.
"""

import argparse
import os
import subprocess
import sys
import time
import socket
import platform
from dataclasses import dataclass


@dataclass
class DiskInfo:
    """Storage device information"""

    device: str
    mountpoint: str
    total: int
    used: int
    free: int
    percent: float


@dataclass
class NetworkInfo:
    """Network interface information"""

    name: str
    ipv4: str
    bytes_sent: int
    bytes_recv: int


class SystemMonitor:
    """System resource monitoring utility"""

    def __init__(self, refresh_rate=1.0):
        """
        Initialize system monitor.

        Args:
            refresh_rate (float): Seconds between updates
        """
        self.refresh_rate = refresh_rate
        self._last_net_stats = {}
        self._last_disk_stats = {}

    def _run_command(self, cmd, shell=False):
        """
        Run a shell command and return output.

        Args:
            cmd (list or str): Command to execute
            shell (bool): Use shell execution

        Returns:
            str: Command output
        """
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, shell=shell, check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            print(f"Command failed: {e}", file=sys.stderr)
            return ""

    def _format_bytes(self, bytes_value):
        """
        Convert bytes to human-readable format.

        Args:
            bytes_value (int): Number of bytes

        Returns:
            str: Formatted byte size
        """
        units = ["B", "KiB", "MiB", "GiB", "TiB"]
        size = float(bytes_value)
        unit_index = 0

        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1

        return f"{size:.1f} {units[unit_index]}"

    def get_disk_info(self):
        """
        Collect disk information.

        Returns:
            list: Disk information details
        """
        disks = []
        try:
            # Use df command to get disk usage
            output = self._run_command(["df", "-P", "-k"])

            for line in output.splitlines()[1:]:
                parts = line.split()
                if len(parts) < 6:
                    continue

                disks.append(
                    DiskInfo(
                        device=parts[0],
                        mountpoint=parts[5],
                        total=int(parts[1]) * 1024,
                        used=int(parts[2]) * 1024,
                        free=int(parts[3]) * 1024,
                        percent=float(parts[4].rstrip("%")),
                    )
                )
        except Exception as e:
            print(f"Error collecting disk info: {e}", file=sys.stderr)

        return disks

    def get_network_info(self):
        """
        Collect network interface information.

        Returns:
            list: Network interface details
        """
        interfaces = []
        try:
            # Read network statistics from /proc/net/dev
            with open("/proc/net/dev", "r") as f:
                # Skip header lines
                f.readline()
                f.readline()

                for line in f:
                    if ":" not in line:
                        continue

                    name, stats = line.split(":")
                    name = name.strip()

                    # Skip loopback
                    if name == "lo":
                        continue

                    # Parse network stats
                    stats = stats.split()
                    bytes_recv = int(stats[0])
                    bytes_sent = int(stats[8])

                    # Get IP address
                    try:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                        sock.connect(("8.8.8.8", 80))
                        ipv4 = sock.getsockname()[0]
                        sock.close()
                    except Exception:
                        ipv4 = "N/A"

                    interfaces.append(
                        NetworkInfo(
                            name=name,
                            ipv4=ipv4,
                            bytes_sent=bytes_sent,
                            bytes_recv=bytes_recv,
                        )
                    )
        except Exception as e:
            print(f"Error collecting network info: {e}", file=sys.stderr)

        return interfaces

    def display_disk_info(self, disks):
        """
        Display disk information in a formatted table.

        Args:
            disks (list): List of DiskInfo objects
        """
        print("\nDisk Information:")
        print(
            f"{'Device':<15} {'Mountpoint':<20} {'Total':<10} {'Used':<10} {'Free':<10} {'Use%':<6}"
        )
        print("-" * 75)

        for disk in disks:
            print(
                f"{disk.device[:14]:<15} "
                f"{disk.mountpoint[:19]:<20} "
                f"{self._format_bytes(disk.total):<10} "
                f"{self._format_bytes(disk.used):<10} "
                f"{self._format_bytes(disk.free):<10} "
                f"{disk.percent:>5.1f}%"
            )

    def display_network_info(self, interfaces):
        """
        Display network interface information in a formatted table.

        Args:
            interfaces (list): List of NetworkInfo objects
        """
        print("\nNetwork Interfaces:")
        print(f"{'Interface':<12} {'IPv4':<15} {'RX Bytes':<15} {'TX Bytes':<15}")
        print("-" * 60)

        for iface in interfaces:
            print(
                f"{iface.name:<12} "
                f"{iface.ipv4:<15} "
                f"{self._format_bytes(iface.bytes_recv):<15} "
                f"{self._format_bytes(iface.bytes_sent):<15}"
            )

    def monitor(self):
        """
        Main monitoring loop.
        """
        try:
            while True:
                # Clear screen (works on most Unix/Linux systems)
                os.system("clear")

                # Get and display system information
                disks = self.get_disk_info()
                self.display_disk_info(disks)

                interfaces = self.get_network_info()
                self.display_network_info(interfaces)

                # Wait before next update
                time.sleep(self.refresh_rate)

        except KeyboardInterrupt:
            print("\nMonitoring stopped.")
        except Exception as e:
            print(f"Monitoring error: {e}", file=sys.stderr)


def main():
    """
    Parse arguments and start system monitor.
    """
    parser = argparse.ArgumentParser(description="Simple System Resource Monitor")
    parser.add_argument(
        "-r",
        "--refresh",
        type=float,
        default=1.0,
        help="Refresh interval in seconds (default: 1.0)",
    )

    args = parser.parse_args()

    # Check system compatibility
    if platform.system() != "Linux":
        print("This script is designed for Linux systems.", file=sys.stderr)
        sys.exit(1)

    # Check root privileges
    if os.geteuid() != 0:
        print("This script requires root privileges.", file=sys.stderr)
        sys.exit(1)

    # Start monitoring
    monitor = SystemMonitor(refresh_rate=args.refresh)
    monitor.monitor()


if __name__ == "__main__":
    main()
