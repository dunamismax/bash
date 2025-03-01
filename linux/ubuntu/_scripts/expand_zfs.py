#!/usr/bin/env python3
"""
ZFS Pool Expansion Script

This utility automates expanding ZFS pools to use the full size of their underlying devices.
It:
  • Detects ZFS pools and their devices automatically
  • Enables the autoexpand property if needed
  • Performs online expansion of pools
  • Validates the expansion results
  • Provides detailed reporting

Note: Run this script with root privileges.
"""

import os
import re
import sys
import time
import subprocess
from typing import Any, Dict, List, Optional

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
import pyfiglet

# ------------------------------
# Configuration
# ------------------------------
SIZE_UNITS = {"K": 1024**1, "M": 1024**2, "G": 1024**3, "T": 1024**4, "P": 1024**5}
WAIT_TIME_SECONDS = 10
EXPECTED_SIZE_TIB_LOWER = 1.7  # Lower bound for 2TB drive in TiB
EXPECTED_SIZE_TIB_UPPER = 2.0  # Upper bound for 2TB drive in TiB

# ------------------------------
# Nord‑Themed Styles & Console Setup
# ------------------------------
# Nord color palette example values:
# nord0: #2E3440, nord4: #D8DEE9, nord8: #88C0D0, nord10: #5E81AC, nord11: #BF616A
console = Console()

def print_header(text: str) -> None:
    """Print a striking ASCII art header using pyfiglet."""
    ascii_art = pyfiglet.figlet_format(text, font="slant")
    console.print(ascii_art, style="bold #88C0D0")

def print_section(text: str) -> None:
    """Print a section header."""
    console.print(f"\n[bold #88C0D0]{text}[/bold #88C0D0]")

def print_step(text: str) -> None:
    """Print a step description."""
    console.print(f"[#88C0D0]• {text}[/#88C0D0]")

def print_success(text: str) -> None:
    """Print a success message."""
    console.print(f"[bold #8FBCBB]✓ {text}[/bold #8FBCBB]")

def print_warning(text: str) -> None:
    """Print a warning message."""
    console.print(f"[bold #5E81AC]⚠ {text}[/bold #5E81AC]")

def print_error(text: str) -> None:
    """Print an error message."""
    console.print(f"[bold #BF616A]✗ {text}[/bold #BF616A]")

# ------------------------------
# Helper Functions
# ------------------------------
def run_command(command: str) -> Optional[str]:
    """
    Execute a shell command and return its output as a string.
    
    Args:
        command: The command to execute.
    
    Returns:
        The command's stdout (str) or None on error.
    """
    try:
        print_step(f"Executing: {command}")
        process = subprocess.run(
            command, shell=True, capture_output=True, text=True, check=True
        )
        return process.stdout.strip()
    except subprocess.CalledProcessError as e:
        print_error(f"Error executing command: {command}")
        if e.stdout:
            console.print(f"[dim]Stdout: {e.stdout.strip()}[/dim]")
        if e.stderr:
            console.print(f"[bold #BF616A]Stderr: {e.stderr.strip()}[/bold #BF616A]")
        return None

# ------------------------------
# ZFS Pool Information Functions
# ------------------------------
def get_zpool_status() -> Optional[Dict[str, List[Dict[str, Any]]]]:
    """
    Retrieve ZFS pool status information by parsing output from 'zpool status'.
    
    Returns:
        Dictionary with pool information, or None on failure.
    """
    output = run_command("zpool status")
    if not output:
        return None

    pool_info = {"pools": []}
    current_pool = None

    pool_name_regex = re.compile(r"pool:\s+(.+)")
    state_regex = re.compile(r"state:\s+(.+)")
    capacity_regex = re.compile(r"capacity:.+allocatable\s+([\d.]+)([KMGTP]?)", re.IGNORECASE)

    for line in output.splitlines():
        line = line.strip()
        pool_match = pool_name_regex.match(line)
        if pool_match:
            pool_name = pool_match.group(1).strip()
            current_pool = {"name": pool_name, "vdevs": [], "allocatable": None}
            pool_info["pools"].append(current_pool)
            continue

        if current_pool:
            state_match = state_regex.match(line)
            if state_match:
                current_pool["state"] = state_match.group(1).strip()
                continue

            if line.startswith("NAME") and "STATE" in line:
                continue

            if line and not any(line.startswith(prefix) for prefix in ("errors:", "config:", "capacity:")):
                parts = line.split()
                if len(parts) >= 2 and parts[1] in [
                    "ONLINE", "DEGRADED", "OFFLINE", "FAULTED", "REMOVED", "UNAVAIL"
                ]:
                    vdev_name = parts[0]
                    vdev_state = parts[1]
                    current_pool["vdevs"].append({
                        "type": "disk",
                        "path": vdev_name,
                        "state": vdev_state,
                    })
                    continue

            capacity_match = capacity_regex.search(line)
            if capacity_match:
                size_value = float(capacity_match.group(1))
                size_unit = capacity_match.group(2).upper() if capacity_match.group(2) else ""
                multiplier = SIZE_UNITS.get(size_unit, 1)
                current_pool["allocatable"] = int(size_value * multiplier)

    return pool_info

def get_zfs_list() -> Optional[List[Dict[str, str]]]:
    """
    Retrieve ZFS dataset information.
    
    Returns:
        A list of dictionaries with dataset info or None on error.
    """
    output = run_command("zfs list -o name,used,available,refer,mountpoint -t all -H")
    if not output:
        return None

    datasets = []
    for line in output.strip().split("\n"):
        parts = line.split("\t")
        if len(parts) == 5:
            datasets.append({
                "name": parts[0],
                "used": parts[1],
                "available": parts[2],
                "refer": parts[3],
                "mountpoint": parts[4],
            })
    return datasets

def get_block_device_size(device_path: str) -> Optional[int]:
    """
    Get the size of a block device in bytes using lsblk.
    
    Args:
        device_path: Path to the block device.
    
    Returns:
        Device size in bytes or None if error.
    """
    base_device = re.sub(r"p?\d+$", "", device_path)
    output = run_command(f"lsblk -b -n -o SIZE {base_device}")
    if output:
        try:
            return int(output)
        except ValueError:
            print_warning(f"Could not parse device size from output: '{output}'")
    return None

# ------------------------------
# ZFS Pool Expansion Functions
# ------------------------------
def _set_autoexpand_property(pool_name: str) -> bool:
    """
    Check and enable the autoexpand property for a given ZFS pool.
    
    Args:
        pool_name: Name of the pool.
    
    Returns:
        True if autoexpand is enabled or successfully set, False otherwise.
    """
    current_output = run_command(f"zpool get autoexpand {pool_name}")
    if not current_output:
        return False

    autoexpand_value = None
    match = re.search(rf"{re.escape(pool_name)}\s+autoexpand\s+(\S+)", current_output)
    if match:
        autoexpand_value = match.group(1).strip()
    else:
        if "on" in current_output.lower():
            autoexpand_value = "on"
        elif "off" in current_output.lower():
            autoexpand_value = "off"

    if autoexpand_value is None:
        print_warning(f"Could not parse autoexpand value from: '{current_output}'")
        return False

    if autoexpand_value != "on":
        print_step(f"autoexpand is '{autoexpand_value}'. Enabling it...")
        if run_command(f"zpool set autoexpand=on {pool_name}"):
            print_success("autoexpand property enabled.")
            return True
        else:
            print_error("Failed to enable autoexpand property.")
            return False
    else:
        print_success("autoexpand is already enabled.")
        return True

def expand_zpool(pool_name: str, device_path: str) -> bool:
    """
    Expand a ZFS pool to utilize the full device size.
    
    Steps:
      1. Check/enable autoexpand.
      2. Initiate online expansion.
      3. Verify pool resize.
    
    Args:
        pool_name: Name of the ZFS pool.
        device_path: Underlying device path.
    
    Returns:
        True if expansion succeeded, False otherwise.
    """
    print_header(f"Expanding ZFS Pool: {pool_name}")
    
    print_step("Step 1: Enabling autoexpand property...")
    if not _set_autoexpand_property(pool_name):
        print_warning("Could not set autoexpand property. Continuing anyway...")
    
    print_step("Step 2: Initiating online expansion...")
    if not run_command(f"zpool online -e {pool_name} {device_path}"):
        print_error(f"Failed to initiate online expansion for '{device_path}' in pool '{pool_name}'.")
        return False
    print_success(f"Online expansion initiated for '{device_path}' in pool '{pool_name}'.")
    
    print_step("Step 3: Verifying pool resize...")
    return _verify_pool_resize(pool_name)

def _verify_pool_resize(pool_name: str) -> bool:
    """
    Verify pool resizing by comparing allocatable space before and after expansion.
    
    Args:
        pool_name: Name of the pool.
    
    Returns:
        True if pool size increased (or unchanged, if already expanded), False otherwise.
    """
    print_step("Retrieving initial pool status...")
    initial_status = get_zpool_status()
    if not initial_status:
        print_error("Failed to retrieve initial zpool status.")
        return False

    initial_pool = next((p for p in initial_status["pools"] if p["name"] == pool_name), None)
    if not initial_pool:
        print_error(f"Pool '{pool_name}' not found in initial status.")
        return False

    initial_size = initial_pool.get("allocatable")
    print(f"Initial allocatable pool size: {bytes_to_human_readable(initial_size)}")
    
    print_step(f"Waiting {WAIT_TIME_SECONDS} seconds for background resizing...")
    time.sleep(WAIT_TIME_SECONDS)
    
    print_step("Retrieving final pool status...")
    final_status = get_zpool_status()
    if not final_status:
        print_error("Failed to retrieve final zpool status.")
        return False

    final_pool = next((p for p in final_status["pools"] if p["name"] == pool_name), None)
    if not final_pool:
        print_error(f"Pool '{pool_name}' not found in final status.")
        return False

    final_size = final_pool.get("allocatable")
    print(f"Final allocatable pool size: {bytes_to_human_readable(final_size)}")
    
    if final_size is None or initial_size is None:
        print_error("Could not compare pool sizes due to parsing issues.")
        return False

    if final_size >= initial_size:
        print_success(f"Pool '{pool_name}' successfully resized (or already fully expanded).")
        return True
    else:
        print_warning(f"Pool size appears to have decreased from {bytes_to_human_readable(initial_size)} to {bytes_to_human_readable(final_size)}.")
        return False

def validate_expansion() -> bool:
    """
    Validate ZFS pool expansion by comparing reported sizes to expected values.
    
    Returns:
        True if the pool size is within expected limits, False otherwise.
    """
    print_section("Validating ZFS Expansion")
    zpool_info = get_zpool_status()
    zfs_datasets = get_zfs_list()

    if not zpool_info or not zfs_datasets:
        print_error("Failed to retrieve pool or dataset information for validation.")
        return False

    total_pool_size = None
    if zpool_info["pools"]:
        # Prefer 'rpool' if available, otherwise first pool.
        pool_to_check = next((p for p in zpool_info["pools"] if p["name"] == "rpool"), zpool_info["pools"][0])
        total_pool_size = pool_to_check.get("allocatable")
        pool_name = pool_to_check.get("name", "unknown")

    print(f"Total Pool Size (zpool): {bytes_to_human_readable(total_pool_size)}")

    # Summarize dataset usage.
    total_used = 0
    total_available = 0
    print_section("ZFS Datasets Summary:")
    for dataset in zfs_datasets:
        console.print(f"  Dataset: [bold]{dataset['name']}[/bold]")
        console.print(f"    Used: {dataset['used']}")
        console.print(f"    Available: {dataset['available']}")
        console.print(f"    Mountpoint: {dataset['mountpoint']}")
        try:
            total_used += convert_size_to_bytes(dataset["used"])
        except ValueError:
            print_warning(f"Could not parse used space '{dataset['used']}' for dataset {dataset['name']}")
        if dataset["available"] != "-":
            try:
                total_available += convert_size_to_bytes(dataset["available"])
            except ValueError:
                print_warning(f"Could not parse available space '{dataset['available']}' for dataset {dataset['name']}")

    print_section("Summary:")
    console.print(f"Total Used Space (datasets): {bytes_to_human_readable(total_used)}")
    console.print(f"Total Available Space (datasets): {bytes_to_human_readable(total_available)}")
    
    expected_lower = EXPECTED_SIZE_TIB_LOWER * (1024**4)
    if total_pool_size is not None and total_pool_size > expected_lower:
        print_success(f"Pool size ({bytes_to_human_readable(total_pool_size)}) is within expected range for a 2TB drive.")
        return True
    else:
        print_warning(f"Pool size ({bytes_to_human_readable(total_pool_size)}) is smaller than expected for a 2TB drive.")
        return False

# ------------------------------
# Size Conversion Helpers
# ------------------------------
def convert_size_to_bytes(size_str: str) -> int:
    """
    Convert a human-readable size string (e.g., '100K', '1G') to bytes.
    
    Args:
        size_str: The size string.
    
    Returns:
        Size in bytes.
    
    Raises:
        ValueError: If the size cannot be parsed.
    """
    size_str = size_str.upper().strip()
    if size_str in ["0", "0B", "-", "NONE"]:
        return 0
    if size_str[-1] in SIZE_UNITS:
        try:
            value = float(size_str[:-1])
            return int(value * SIZE_UNITS[size_str[-1]])
        except ValueError:
            raise ValueError(f"Invalid size format: {size_str}")
    else:
        try:
            return int(size_str)
        except ValueError:
            raise ValueError(f"Invalid size format: {size_str}")

def bytes_to_human_readable(bytes_val: Optional[int]) -> str:
    """
    Convert a byte value to a human-readable string.
    
    Args:
        bytes_val: The number of bytes.
    
    Returns:
        A formatted string (e.g., '1.23 GB').
    """
    if bytes_val is None:
        return "N/A"
    if bytes_val == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(bytes_val)
    idx = 0
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024
        idx += 1
    return f"{size:.2f} {units[idx]}"

# ------------------------------
# Main CLI Entry Point with Click
# ------------------------------
@click.command()
def main() -> None:
    """
    ZFS Pool Expansion Script - Nord Themed CLI

    Automates expanding ZFS pools to utilize the full size of underlying devices.
    """
    print_header("ZFS Pool Expansion")
    console.print(f"Started at: [bold #D8DEE9]{time.strftime('%Y-%m-%d %H:%M:%S')}[/bold #D8DEE9]")

    if os.geteuid() != 0:
        print_error("This script requires root privileges. Please run with sudo.")
        sys.exit(1)

    pool_status = get_zpool_status()
    if not pool_status or not pool_status["pools"]:
        print_error("Could not retrieve ZFS pool status or no pools found. Ensure ZFS is configured.")
        sys.exit(1)

    pools = pool_status["pools"]
    # For example, we expect pools 'bpool' and 'rpool'
    expected_pools = ["bpool", "rpool"]
    found_pools = [p["name"] for p in pools]
    if set(found_pools) != set(expected_pools):
        print_warning(f"Expected pools {expected_pools} but found {found_pools}. Proceed with caution.")

    pool_device_paths: Dict[str, str] = {}
    expansion_results: Dict[str, bool] = {}

    for pool in pools:
        pool_name = pool["name"]
        vdevs = pool.get("vdevs", [])
        if not vdevs:
            print_warning(f"No vdevs found for pool '{pool_name}'. Skipping.")
            continue
        device_path = vdevs[0].get("path")
        if not device_path:
            print_warning(f"Could not determine device for pool '{pool_name}'. Skipping.")
            continue
        pool_device_paths[pool_name] = device_path

    print_section("Detected ZFS Pools and Devices")
    for name, dev in pool_device_paths.items():
        console.print(f"  Pool: [bold]{name}[/bold], Device: [italic]{dev}[/italic]")

    if not pool_device_paths:
        print_error("No valid pool-device pairs found. Aborting expansion.")
        sys.exit(1)

    print_section("Starting ZFS Pool Expansion Process")
    for pool_name, device_path in pool_device_paths.items():
        result = expand_zpool(pool_name, device_path)
        expansion_results[pool_name] = result

    print_section("Expansion Process Completed")
    validation = validate_expansion()

    print_section("Expansion Results Summary")
    for pool_name, success in expansion_results.items():
        status_text = "Successful" if success else "Failed"
        console.print(f"  Pool [bold]{pool_name}[/bold]: {status_text}")

    overall = "Successful" if all(expansion_results.values()) and validation else "Failed"
    console.print(f"Overall validation: [bold]{overall}[/bold]")
    console.print(f"Completed at: [bold #D8DEE9]{time.strftime('%Y-%m-%d %H:%M:%S')}[/bold #D8DEE9]")

    sys.exit(0 if all(expansion_results.values()) and validation else 1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_warning("\nOperation cancelled by user.")
        sys.exit(130)
    except Exception as e:
        print_error(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)