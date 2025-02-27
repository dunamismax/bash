#!/usr/bin/env python3
"""
Simple Network Information and Diagnostics Tool

A lightweight Python script for basic network analysis and connectivity testing.

Usage:
    python network_toolkit.py [option]
"""

import argparse
import os
import re
import socket
import subprocess
import sys
import time


class NetworkToolkit:
    """
    A collection of network diagnostic and information gathering methods.
    """

    @staticmethod
    def get_network_interfaces():
        """
        Retrieve network interface information.

        Returns:
            list: Network interfaces with their details
        """
        interfaces = []
        try:
            output = subprocess.check_output(["ip", "link"], universal_newlines=True)
            for line in output.splitlines():
                match = re.search(r"^\d+:\s+([^:@]+).*state\s+(\w+)", line)
                if match:
                    iface_name, state = match.groups()
                    if iface_name != "lo":
                        interfaces.append({"name": iface_name, "status": state})
        except Exception as e:
            print(f"Error retrieving network interfaces: {e}", file=sys.stderr)
        return interfaces

    @staticmethod
    def get_ip_addresses(interface=None):
        """
        Retrieve IP addresses for network interfaces.

        Args:
            interface (str, optional): Specific interface to query

        Returns:
            dict: IP addresses for interfaces
        """
        ip_addresses = {}
        try:
            cmd = ["ip", "-o", "addr"]
            if interface:
                cmd.extend(["show", "dev", interface])
            output = subprocess.check_output(cmd, universal_newlines=True)

            for line in output.splitlines():
                parts = line.split()
                if len(parts) >= 4:
                    iface = parts[1]
                    if iface == "lo":
                        continue

                    # Look for IPv4 and IPv6 addresses
                    if "inet " in line:
                        ip_match = re.search(r"inet\s+([^/]+)", line)
                        if ip_match:
                            ip_addresses.setdefault(iface, []).append(
                                {"type": "IPv4", "address": ip_match.group(1)}
                            )

                    if "inet6 " in line:
                        ip_match = re.search(r"inet6\s+([^/]+)", line)
                        if ip_match and not ip_match.group(1).startswith("fe80"):
                            ip_addresses.setdefault(iface, []).append(
                                {"type": "IPv6", "address": ip_match.group(1)}
                            )
        except Exception as e:
            print(f"Error retrieving IP addresses: {e}", file=sys.stderr)
        return ip_addresses

    @staticmethod
    def ping(target, count=4):
        """
        Perform ping test to a target.

        Args:
            target (str): Hostname or IP to ping
            count (int, optional): Number of ping attempts

        Returns:
            dict: Ping test results
        """
        try:
            cmd = ["ping", "-c", str(count), target]
            output = subprocess.check_output(cmd, universal_newlines=True)

            # Parse ping results
            results = {
                "target": target,
                "sent": 0,
                "received": 0,
                "packet_loss": "0%",
                "rtt_min": "0 ms",
                "rtt_avg": "0 ms",
                "rtt_max": "0 ms",
            }

            # Extract packet statistics
            for line in output.splitlines():
                # Transmitted and received packets
                sent_match = re.search(
                    r"(\d+) packets transmitted, (\d+) received", line
                )
                if sent_match:
                    results["sent"] = int(sent_match.group(1))
                    results["received"] = int(sent_match.group(2))

                # Packet loss
                loss_match = re.search(r"(\d+)% packet loss", line)
                if loss_match:
                    results["packet_loss"] = f"{loss_match.group(1)}%"

                # Round-trip time
                rtt_match = re.search(
                    r"min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)", line
                )
                if rtt_match:
                    results["rtt_min"] = f"{rtt_match.group(1)} ms"
                    results["rtt_avg"] = f"{rtt_match.group(2)} ms"
                    results["rtt_max"] = f"{rtt_match.group(3)} ms"

            return results
        except subprocess.CalledProcessError as e:
            print(f"Ping failed: {e}", file=sys.stderr)
            return None

    @staticmethod
    def traceroute(target, max_hops=30):
        """
        Perform traceroute to a target.

        Args:
            target (str): Hostname or IP to trace
            max_hops (int, optional): Maximum number of hops

        Returns:
            list: Traceroute hops with details
        """
        try:
            cmd = ["traceroute", "-m", str(max_hops), target]
            output = subprocess.check_output(cmd, universal_newlines=True)

            hops = []
            for line in output.splitlines()[1:]:  # Skip header
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        hop_num = parts[0]
                        host = parts[1] if parts[1] != "*" else "Unknown"

                        # Extract times if available
                        times = []
                        for p in parts[2:]:
                            try:
                                time_val = float(p.rstrip(" ms"))
                                times.append(time_val)
                            except (ValueError, IndexError):
                                break

                        avg_time = sum(times) / len(times) if times else None

                        hops.append(
                            {
                                "hop": hop_num,
                                "host": host,
                                "times": times,
                                "avg_time": f"{avg_time:.2f} ms"
                                if avg_time is not None
                                else "N/A",
                            }
                        )
                    except Exception:
                        continue

            return hops
        except subprocess.CalledProcessError as e:
            print(f"Traceroute failed: {e}", file=sys.stderr)
            return None

    @staticmethod
    def dns_lookup(hostname):
        """
        Perform DNS lookup for a hostname.

        Args:
            hostname (str): Hostname to resolve

        Returns:
            dict: DNS resolution details
        """
        try:
            # Get IP addresses
            addrs = socket.getaddrinfo(hostname, None)

            # Organize results
            results = {"hostname": hostname, "ipv4": [], "ipv6": []}

            for addr in addrs:
                ip = addr[4][0]
                if ":" in ip:
                    results["ipv6"].append(ip)
                else:
                    results["ipv4"].append(ip)

            return results
        except socket.gaierror as e:
            print(f"DNS lookup failed: {e}", file=sys.stderr)
            return None


def main():
    """
    Main entry point for the network toolkit.
    """
    parser = argparse.ArgumentParser(description="Simple Network Diagnostics Tool")
    parser.add_argument(
        "-i", "--interfaces", action="store_true", help="List network interfaces"
    )
    parser.add_argument("-p", "--ping", type=str, help="Ping a target host")
    parser.add_argument(
        "-t", "--traceroute", type=str, help="Traceroute to a target host"
    )
    parser.add_argument("-d", "--dns", type=str, help="Perform DNS lookup")
    parser.add_argument(
        "--count", type=int, default=4, help="Number of ping attempts (default: 4)"
    )
    parser.add_argument(
        "--max-hops",
        type=int,
        default=30,
        help="Maximum hops for traceroute (default: 30)",
    )

    args = parser.parse_args()

    # Validate root privileges for some network commands
    if os.geteuid() != 0:
        print("Warning: Some operations may require root privileges.", file=sys.stderr)

    # Execute requested operations
    if args.interfaces:
        print("Network Interfaces:")
        interfaces = NetworkToolkit.get_network_interfaces()
        for iface in interfaces:
            print(f"  {iface['name']}: {iface['status']}")

        print("\nIP Addresses:")
        ip_addresses = NetworkToolkit.get_ip_addresses()
        for iface, addrs in ip_addresses.items():
            print(f"  {iface}:")
            for addr in addrs:
                print(f"    {addr['type']}: {addr['address']}")

    if args.ping:
        print(f"\nPing Results for {args.ping}:")
        results = NetworkToolkit.ping(args.ping, args.count)
        if results:
            for key, value in results.items():
                print(f"  {key.replace('_', ' ').title()}: {value}")

    if args.traceroute:
        print(f"\nTraceroute to {args.traceroute}:")
        hops = NetworkToolkit.traceroute(args.traceroute, args.max_hops)
        if hops:
            for hop in hops:
                print(
                    f"  Hop {hop['hop']}: {hop['host']} (Avg Time: {hop['avg_time']})"
                )

    if args.dns:
        print(f"\nDNS Lookup for {args.dns}:")
        results = NetworkToolkit.dns_lookup(args.dns)
        if results:
            print(f"  Hostname: {results['hostname']}")
            print("  IPv4 Addresses:")
            for ip in results.get("ipv4", []):
                print(f"    - {ip}")
            print("  IPv6 Addresses:")
            for ip in results.get("ipv6", []):
                print(f"    - {ip}")


if __name__ == "__main__":
    main()
