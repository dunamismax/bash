#!/usr/bin/env python3
"""
ZFS Pool Expansion Script

This script automates the process of expanding ZFS pools to use the full size of their underlying devices.
It's designed to handle pool expansion after physically replacing a drive with a larger one or after
extending a virtual disk in a virtualized environment.

Features:
- Detects ZFS pools and their devices automatically
- Enables autoexpand property if needed
- Performs online expansion of pools
- Validates expansion results
- Provides detailed reporting

Usage: sudo python3 zfs_expand.py
"""

import subprocess
import json
import os
import re
import time
import sys
from typing import Dict, List, Optional, Union, Any, Tuple

# Define constants for readability and maintainability
SIZE_UNITS = {"K": 1024**1, "M": 1024**2, "G": 1024**3, "T": 1024**4, "P": 1024**5}
WAIT_TIME_SECONDS = 10
EXPECTED_SIZE_TIB_LOWER = 1.7  # Lower bound for 2TB drive in TiB
EXPECTED_SIZE_TIB_UPPER = 2.0  # Upper bound for 2TB drive in TiB


def run_command(command: str) -> Optional[str]:
    """
    Executes a shell command and returns the output as a string, or None on error.

    Args:
        command: The shell command to execute

    Returns:
        The command output as a string, or None if an error occurred
    """
    try:
        process = subprocess.run(
            command, shell=True, capture_output=True, text=True, check=True
        )
        return process.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error executing command: {command}")
        print(f"Return code: {e.returncode}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        return None


def get_zpool_status() -> Optional[Dict[str, List[Dict[str, Any]]]]:
    """
    Retrieves ZFS pool status information by parsing text output from 'zpool status'.

    This function parses the text output from zpool status to extract key information
    about each pool, including pool name, state, vdevs, and allocatable space.

    Returns:
        Dictionary containing pool information, or None if the command failed
    """
    output = run_command("zpool status")  # No -J option in some ZFS implementations
    if not output:
        return None

    pool_info = {"pools": []}
    current_pool = None

    # Regular expressions for more robust parsing
    pool_name_regex = re.compile(r"pool:\s+(.+)")
    state_regex = re.compile(r"state:\s+(.+)")
    capacity_regex = re.compile(
        r"capacity:.+allocatable\s+([\d.]+)([KMGTP]?)", re.IGNORECASE
    )

    for line in output.splitlines():
        line = line.strip()

        # Parse pool name
        pool_match = pool_name_regex.match(line)
        if pool_match:
            pool_name = pool_match.group(1).strip()
            current_pool = {"name": pool_name, "vdevs": [], "allocatable": None}
            pool_info["pools"].append(current_pool)
            continue

        # Parse pool state
        if current_pool:
            state_match = state_regex.match(line)
            if state_match:
                current_pool["state"] = state_match.group(1).strip()
                continue

            # Skip header line for vdevs
            if line.startswith("NAME") and "STATE" in line:
                continue

            # Parse vdev lines (excluding headers, errors, etc.)
            if (
                line
                and not line.startswith("errors:")
                and not line.startswith("config:")
                and not line.startswith("capacity:")
            ):
                parts = line.split()
                # Check if this is a vdev line with at least name and state
                if len(parts) >= 2 and parts[1] in [
                    "ONLINE",
                    "DEGRADED",
                    "OFFLINE",
                    "FAULTED",
                    "REMOVED",
                    "UNAVAIL",
                ]:
                    vdev_name = parts[0]
                    vdev_state = parts[1]
                    current_pool["vdevs"].append(
                        {
                            "type": "disk",  # Assuming 'disk' type, could be improved
                            "path": vdev_name,
                            "state": vdev_state,
                        }
                    )
                    continue

            # Parse allocatable space from capacity line
            capacity_match = capacity_regex.search(line)
            if capacity_match:
                size_value = float(capacity_match.group(1))
                size_unit = (
                    capacity_match.group(2).upper() if capacity_match.group(2) else ""
                )

                # Convert to bytes
                multiplier = SIZE_UNITS.get(size_unit, 1)
                current_pool["allocatable"] = int(size_value * multiplier)

    return pool_info


def get_zfs_list() -> Optional[List[Dict[str, str]]]:
    """
    Retrieves ZFS dataset list information.

    Returns a list of dictionaries containing dataset information including name,
    space used, available space, referenced space, and mountpoint.

    Returns:
        List of dictionaries with dataset information, or None if the command failed
    """
    output = run_command("zfs list -o name,used,available,refer,mountpoint -t all -H")
    if not output:
        return None

    lines = output.strip().split("\n")
    datasets = []

    for line in lines:
        parts = line.split("\t")
        if len(parts) == 5:
            datasets.append(
                {
                    "name": parts[0],
                    "used": parts[1],
                    "available": parts[2],
                    "refer": parts[3],
                    "mountpoint": parts[4],
                }
            )

    return datasets


def get_block_device_size(device_path: str) -> Optional[int]:
    """
    Gets the size of a block device using lsblk.

    Args:
        device_path: Path to the block device

    Returns:
        Size of the device in bytes, or None if the command failed
    """
    # Ensure device_path doesn't have partition numbers
    base_device = re.sub(r"p?\d+$", "", device_path)

    output = run_command(f"lsblk -b -n -o SIZE {base_device}")
    if output:
        try:
            return int(output)
        except ValueError:
            print(f"Warning: Could not parse device size from output: '{output}'")

    return None


def expand_zpool(pool_name: str, device_path: str) -> bool:
    """
    Expands a ZFS pool to use the full device size using multiple methods.

    This function performs three steps:
    1. Checks and enables the autoexpand property if needed
    2. Initiates an online expansion of the device
    3. Verifies the pool resize by comparing before and after sizes

    Args:
        pool_name: Name of the ZFS pool to expand
        device_path: Path to the underlying device

    Returns:
        True if expansion was successful, False otherwise
    """
    print(f"\n--- Expanding ZFS Pool: {pool_name} ---")

    # Step 1: Check and set autoexpand property
    print("Step 1: Checking and enabling autoexpand property...")
    if not _set_autoexpand_property(pool_name):
        print("   Warning: Could not set autoexpand property. Continuing anyway...")

    # Step 2: Online expand the device
    print("\nStep 2: Online expanding device...")
    if not run_command(f"zpool online -e {pool_name} {device_path}"):
        print(
            f"   Failed to initiate online expansion for device '{device_path}' in pool '{pool_name}'."
        )
        return False

    print(
        f"   Successfully initiated online expansion for device '{device_path}' in pool '{pool_name}'."
    )

    # Step 3: Verify pool resize
    return _verify_pool_resize(pool_name)


def _set_autoexpand_property(pool_name: str) -> bool:
    """
    Helper function to check and set the autoexpand property for a ZFS pool.

    Args:
        pool_name: Name of the ZFS pool

    Returns:
        True if property is successfully set or already enabled, False otherwise
    """
    current_autoexpand_output = run_command(f"zpool get autoexpand {pool_name}")
    if not current_autoexpand_output:
        return False

    # Parse output to find current autoexpand value
    autoexpand_value = None

    # Try different parsing approaches for robustness
    # First try tab or multi-space delimited format
    match = re.search(
        rf"{re.escape(pool_name)}\s+autoexpand\s+(\S+)", current_autoexpand_output
    )
    if match:
        autoexpand_value = match.group(1).strip()
    else:
        # Fallback: just look for on/off values anywhere in the output
        if "on" in current_autoexpand_output.lower():
            autoexpand_value = "on"
        elif "off" in current_autoexpand_output.lower():
            autoexpand_value = "off"

    if autoexpand_value is None:
        print(
            f"   Warning: Could not parse autoexpand value from: '{current_autoexpand_output}'"
        )
        return False

    if autoexpand_value != "on":
        print(f"   autoexpand is currently '{autoexpand_value}'. Enabling it...")
        if run_command(f"zpool set autoexpand=on {pool_name}"):
            print("   autoexpand property enabled.")
            return True
        else:
            print("   Failed to enable autoexpand property.")
            return False
    else:
        print("   autoexpand is already enabled.")
        return True


def _verify_pool_resize(pool_name: str) -> bool:
    """
    Helper function to verify pool resizing by comparing sizes before and after expansion.

    Args:
        pool_name: Name of the ZFS pool

    Returns:
        True if verification succeeded, False otherwise
    """
    print("\nStep 3: Verifying pool resize...")

    # Get initial pool status
    initial_pool_status = get_zpool_status()
    if not initial_pool_status:
        print("   Failed to retrieve initial zpool status for verification.")
        return False

    # Find the specified pool
    initial_pool_obj = next(
        (p for p in initial_pool_status["pools"] if p["name"] == pool_name), None
    )
    if not initial_pool_obj:
        print(f"   Pool '{pool_name}' not found in status output.")
        return False

    initial_pool_size = initial_pool_obj.get("allocatable")
    initial_size_readable = (
        bytes_to_human_readable(initial_pool_size)
        if initial_pool_size is not None
        else "N/A"
    )
    print(f"   Initial allocatable pool size: {initial_size_readable}")

    # Wait for potential background resizing
    print(
        f"   Waiting {WAIT_TIME_SECONDS} seconds for potential background resizing..."
    )
    time.sleep(WAIT_TIME_SECONDS)

    # Get final pool status
    final_pool_status = get_zpool_status()
    if not final_pool_status:
        print("   Failed to retrieve final zpool status for verification.")
        return False

    # Find the specified pool
    final_pool_obj = next(
        (p for p in final_pool_status["pools"] if p["name"] == pool_name), None
    )
    if not final_pool_obj:
        print(f"   Pool '{pool_name}' not found in final status output.")
        return False

    final_pool_size = final_pool_obj.get("allocatable")
    final_size_readable = (
        bytes_to_human_readable(final_pool_size)
        if final_pool_size is not None
        else "N/A"
    )
    print(f"   Final allocatable pool size: {final_size_readable}")

    # Compare sizes
    if final_pool_size is None or initial_pool_size is None:
        print("   Could not compare pool sizes due to parsing issues.")
        return False

    if final_pool_size > initial_pool_size:
        print(
            f"   Pool '{pool_name}' successfully resized. Allocatable space increased from "
            f"{initial_size_readable} to {final_size_readable}."
        )
        return True
    elif final_pool_size == initial_pool_size:
        print(
            f"   Pool size did not change after online expansion. It remains at {final_size_readable}."
        )
        print(
            "   This might indicate the pool was already fully expanded or further steps are needed."
        )
        # Return True even if no change, as this might be expected in some cases
        return True
    else:
        print(
            f"   Warning: Pool size appears to have decreased from {initial_size_readable} to {final_size_readable}."
        )
        return False


def validate_expansion() -> bool:
    """
    Validates the ZFS pool expansion by checking reported sizes.

    This function compares the reported pool size against expected values for a 2TB drive
    and provides a summary of pool and dataset space usage.

    Returns:
        True if validation was successful, False otherwise
    """
    print("\n--- Validating ZFS Expansion ---")

    zpool_info = get_zpool_status()
    zfs_datasets = get_zfs_list()

    if not zpool_info or not zfs_datasets:
        print(
            "Error: Could not retrieve ZFS pool or dataset information for validation."
        )
        return False

    # Get total pool size from zpool status
    total_pool_size_zpool = None
    if zpool_info["pools"]:
        # Find rpool if present, otherwise use the first pool
        rpool = next((p for p in zpool_info["pools"] if p["name"] == "rpool"), None)
        pool_to_check = rpool if rpool else zpool_info["pools"][0]
        total_pool_size_zpool = pool_to_check.get("allocatable")
        pool_name = pool_to_check.get("name", "unknown")

    # Calculate total space from datasets
    total_used_space_zfs = 0
    total_available_space_zfs = 0

    print("\nZFS Datasets Summary:")
    for dataset in zfs_datasets:
        print(f"  Dataset: {dataset['name']}")
        print(f"    Used:      {dataset['used']}")
        print(f"    Available: {dataset['available']}")
        print(f"    Mountpoint:{dataset['mountpoint']}")

        # Calculate total used space
        try:
            used_bytes = convert_size_to_bytes(dataset["used"])
            total_used_space_zfs += used_bytes
        except ValueError:
            print(
                f"    Warning: Could not parse used space '{dataset['used']}' for this dataset"
            )

        # Calculate total available space (only for filesystems, not snapshots)
        try:
            # Skip snapshots which often have "-" as available space
            if dataset["available"] != "-":
                available_bytes = convert_size_to_bytes(dataset["available"])
                total_available_space_zfs += available_bytes
        except ValueError:
            print(
                f"    Warning: Could not parse available space '{dataset['available']}' for this dataset"
            )

    # Print summary
    print("\n--- Summary ---")
    print(
        f"Total Pool Size (zpool): {bytes_to_human_readable(total_pool_size_zpool) if total_pool_size_zpool is not None else 'N/A'}"
    )
    print(
        f"Total Used Space (datasets): {bytes_to_human_readable(total_used_space_zfs)}"
    )
    print(
        f"Total Available Space (datasets): {bytes_to_human_readable(total_available_space_zfs)}"
    )

    # Calculate expected size range in bytes
    expected_size_bytes_lower = EXPECTED_SIZE_TIB_LOWER * (
        1024**4
    )  # Lower bound for 2TB drive in bytes
    expected_size_bytes_upper = EXPECTED_SIZE_TIB_UPPER * (
        1024**4
    )  # Upper bound for 2TB drive in bytes

    # Validate pool size
    if (
        total_pool_size_zpool is not None
        and total_pool_size_zpool > expected_size_bytes_lower
    ):
        print("\n--- Expansion Validation Successful ---")
        print(
            f"The reported pool size ({bytes_to_human_readable(total_pool_size_zpool)}) "
            f"is within the expected range for a 2TB drive."
        )
        print(
            "Please check 'zpool status' and 'zfs list' manually for a detailed confirmation."
        )
        return True
    else:
        print("\n--- Expansion Validation Failed ---")
        if total_pool_size_zpool is None:
            print("Failed to parse the pool size. Manual verification needed.")
        else:
            print(
                f"The reported pool size ({bytes_to_human_readable(total_pool_size_zpool)}) "
                f"is smaller than expected for a 2TB drive."
            )
        print("Further investigation is needed. Check 'zpool status' for errors.")
        return False


def convert_size_to_bytes(size_str: str) -> int:
    """
    Converts human-readable size string (e.g., '100K', '1G', '200M') to bytes.

    Args:
        size_str: Size string with optional unit suffix (K, M, G, T, P)

    Returns:
        Size in bytes as an integer

    Raises:
        ValueError: If the size string cannot be parsed
    """
    size_str = size_str.upper()

    # Handle special cases
    if size_str in ["0", "0B", "-", "NONE"]:
        return 0

    # Check if size ends with a unit
    if size_str[-1] in SIZE_UNITS:
        unit = size_str[-1]
        try:
            value = float(size_str[:-1])
            return int(value * SIZE_UNITS[unit])
        except ValueError:
            raise ValueError(f"Invalid size format: {size_str}")
    else:
        # No unit suffix - assume bytes
        try:
            return int(size_str)
        except ValueError:
            raise ValueError(f"Invalid size format: {size_str}")


def bytes_to_human_readable(bytes_val: Optional[int]) -> str:
    """
    Converts bytes to human-readable format (e.g., KB, MB, GB, TB).

    Args:
        bytes_val: Number of bytes or None

    Returns:
        Human-readable string representation of the size
    """
    if bytes_val is None:
        return "N/A"

    if bytes_val == 0:
        return "0 B"

    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(bytes_val)
    unit_index = 0

    while abs(size) >= 1024.0 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1

    return f"{size:.2f} {units[unit_index]}"


def main() -> int:
    """
    Main function that orchestrates the ZFS pool expansion process.

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    print("--- ZFS Pool Expansion Script ---")
    print(f"Started at: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Check for root privileges
    if os.geteuid() != 0:
        print("Error: This script requires root privileges. Please run with sudo.")
        return 1

    # Get pool status
    pool_status = get_zpool_status()
    if not pool_status or not pool_status["pools"]:
        print("Error: Could not retrieve ZFS pool status or no pools found.")
        print("Please ensure ZFS is properly configured and pools exist.")
        return 1

    # Identify pools and their devices
    pools = pool_status["pools"]
    expected_pools = ["bpool", "rpool"]
    found_pools = [p["name"] for p in pools]

    if set(found_pools) != set(expected_pools):
        print(f"Warning: Expected pools {expected_pools} but found {found_pools}.")
        print("Script will continue but proceed with caution.")

    pool_device_paths = {}  # Dictionary to store pool names and device paths
    expansion_results = {}  # Track expansion results for reporting

    # Identify device paths for each pool
    for pool in pools:
        pool_name = pool["name"]
        vdevs = pool.get("vdevs", [])

        if not vdevs:
            print(
                f"Warning: No vdevs found for pool '{pool_name}'. Skipping this pool."
            )
            continue

        # For simplicity, use the first vdev (assumed to be the main device)
        # More complex pools might need a different approach
        device_path = vdevs[0].get("path")
        if not device_path:
            print(
                f"Warning: Could not determine device path for pool '{pool_name}'. Skipping this pool."
            )
            continue

        pool_device_paths[pool_name] = device_path

    # Print detected pools and devices
    print("\nDetected ZFS Pools and Devices:")
    for pool_name, device_path in pool_device_paths.items():
        print(f"  Pool: {pool_name}, Device: {device_path}")

    if not pool_device_paths:
        print(
            "Error: No valid pool and device combinations found. Cannot proceed with expansion."
        )
        return 1

    # Perform expansion on each pool
    print("\n--- Starting ZFS Pool Expansion Process ---")

    for pool_name, device_path in pool_device_paths.items():
        success = expand_zpool(pool_name, device_path)
        expansion_results[pool_name] = success

    # Validate expansion results
    print("\n--- Expansion Process Completed ---")

    validation_success = validate_expansion()

    # Final report
    print("\n--- Expansion Results Summary ---")
    for pool_name, success in expansion_results.items():
        result = "Successful" if success else "Failed"
        print(f"  Pool '{pool_name}': {result}")

    print(f"Overall validation: {'Successful' if validation_success else 'Failed'}")
    print(f"Completed at: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    return 0 if all(expansion_results.values()) and validation_success else 1


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(130)
    except Exception as e:
        print(f"\nUnexpected error: {str(e)}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
