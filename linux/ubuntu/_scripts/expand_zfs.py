#!/usr/bin/env python3

import subprocess
import json
import os
import re  # Import the regular expression module


def run_command(command):
    """Executes a shell command and returns the output as a string, or None on error."""
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


def get_zpool_status():
    """Retrieves ZFS pool status information by parsing text output."""
    output = run_command("zpool status")  # No -J option
    if not output:
        return None

    pool_info = {"pools": []}
    current_pool = None

    for line in output.splitlines():
        line = line.strip()
        if line.startswith("pool:"):
            pool_name = line.split(":")[1].strip()
            current_pool = {
                "name": pool_name,
                "vdevs": [],
                "allocatable": None,
            }  # Initialize allocatable to None
            pool_info["pools"].append(current_pool)
        elif line.startswith("state:") and current_pool:
            current_pool["state"] = line.split(":")[1].strip()
        elif line.startswith("NAME") and current_pool and "STATE" in line:
            continue  # Skip header line for vdevs
        elif (
            line
            and current_pool
            and not line.startswith("errors:")
            and not line.startswith("config:")
            and not line.startswith("capacity:")
        ):  # Vdev lines (excluding errors, config header, capacity)
            parts = line.split()
            if (
                len(parts) >= 2 and parts[1] == "ONLINE"
            ):  # Assuming vdev line and ONLINE state
                vdev_name = parts[0]
                current_pool["vdevs"].append(
                    {"type": "disk", "path": vdev_name, "state": "ONLINE"}
                )  # Assuming 'disk' type
        elif (
            line.startswith("capacity:") and current_pool
        ):  # Parse capacity line to get allocatable
            # Example capacity line: "capacity:  22%  ... allocatable 1.58T ..."
            match = re.search(
                r"allocatable\s+([\d.]+)([KMGTP]?)", line, re.IGNORECASE
            )  # Regex to find "allocatable" followed by size
            if match:
                size_value = float(match.group(1))
                size_unit = match.group(2).upper()
                multiplier = 1
                if size_unit == "K":
                    multiplier = 1024**1
                elif size_unit == "M":
                    multiplier = 1024**2
                elif size_unit == "G":
                    multiplier = 1024**3
                elif size_unit == "T":
                    multiplier = 1024**4
                elif size_unit == "P":
                    multiplier = 1024**5
                current_pool["allocatable"] = int(
                    size_value * multiplier
                )  # Store allocatable in bytes

    return pool_info


def get_zfs_list():
    """Retrieves ZFS dataset list information."""
    output = run_command("zfs list -o name,used,available,refer,mountpoint -t all -H")
    if output:
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
    return None


def get_block_device_size(device_path):
    """Gets the size of a block device using lsblk."""
    output = run_command(f"lsblk -b -n -o SIZE {device_path}")
    if output:
        return int(output)
    return None


def expand_zpool(pool_name, device_path):  # Modified to accept device_path
    """Expands a ZFS pool to use the full device size using multiple methods."""

    print(f"\n--- Expanding ZFS Pool: {pool_name} ---")

    # 1. Check and set autoexpand property
    print("Step 1: Checking and enabling autoexpand property...")
    current_autoexpand_output = run_command(
        f"zpool get autoexpand {pool_name}"
    )  # Get full output line
    if current_autoexpand_output:
        autoexpand_value = current_autoexpand_output.split("\t")[
            2
        ].strip()  # Parse more robustly
        if autoexpand_value != "on":
            print(f"   autoexpand is currently '{autoexpand_value}'. Enabling it...")
            if run_command(f"zpool set autoexpand=on {pool_name}"):
                print("   autoexpand property enabled.")
            else:
                print(
                    "   Failed to enable autoexpand property. Expansion might not be fully automatic."
                )
        else:
            print("   autoexpand is already enabled.")
    else:
        print(
            "   Failed to get autoexpand property. Skipping autoexpand check/enable."
        )  # Handle failure to get property

    # 2. Online expand the device
    print("\nStep 2: Online expanding device...")
    if run_command(
        f"zpool online -e {pool_name} {device_path}"
    ):  # Use device_path here
        print(
            f"   Successfully initiated online expansion for device '{device_path}' in pool '{pool_name}'."
        )
    else:
        print(
            f"   Failed to initiate online expansion for device '{device_path}' in pool '{pool_name}'."
        )

    # 3. Verify pool resize (check zpool status and zpool list)
    print("\nStep 3: Verifying pool resize...")
    initial_pool_status = get_zpool_status()
    if initial_pool_status and pool_name in [
        p["name"] for p in initial_pool_status["pools"]
    ]:
        initial_pool_obj = next(
            p for p in initial_pool_status["pools"] if p["name"] == pool_name
        )  # Get pool object
        initial_pool_size = initial_pool_obj["allocatable"]  # Get allocatable size
        print(
            f"   Initial allocatable pool size: {bytes_to_human_readable(initial_pool_size) if initial_pool_size is not None else 'N/A (parsing issue)'}"
        )

        # Wait a moment for potential background resizing to complete (important for some systems)
        print("   Waiting a few seconds for potential background resizing...")
        import time

        time.sleep(10)  # Wait 10 seconds, adjust if needed

        final_pool_status = get_zpool_status()
        if final_pool_status and pool_name in [
            p["name"] for p in final_pool_status["pools"]
        ]:
            final_pool_obj = next(
                p for p in final_pool_status["pools"] if p["name"] == pool_name
            )
            final_pool_size = final_pool_obj["allocatable"]
            print(
                f"   Final allocatable pool size: {bytes_to_human_readable(final_pool_size) if final_pool_size is not None else 'N/A (parsing issue)'}"
            )

            if (
                final_pool_size is not None
                and initial_pool_size is not None
                and final_pool_size > initial_pool_size
            ):
                print(
                    f"   Pool '{pool_name}' successfully resized. Allocatable space increased from {bytes_to_human_readable(initial_pool_size)} to {bytes_to_human_readable(final_pool_size)}."
                )
            elif final_pool_size == initial_pool_size:
                print(
                    f"   Pool size did not change after online expansion. It remains at {bytes_to_human_readable(final_pool_size) if final_pool_size is not None else 'N/A'}. This might indicate the pool was already fully expanded or further steps are needed (manual partition resizing)."
                )
            else:
                print(
                    f"   Pool size verification inconclusive or parsing failed. Initial size: {bytes_to_human_readable(initial_pool_size) if initial_pool_size is not None else 'N/A'}, Final size: {bytes_to_human_readable(final_pool_size) if final_pool_size is not None else 'N/A'}. Please check zpool status manually."
                )
        else:
            print(
                "   Failed to retrieve final zpool status for verification or pool not found in status output."
            )
    else:
        print(
            "   Failed to retrieve initial zpool status for verification or pool not found in status output."
        )


def validate_expansion():
    """Validates the ZFS pool expansion by checking reported sizes."""
    print("\n--- Validating ZFS Expansion ---")

    zpool_info = get_zpool_status()
    zfs_datasets = get_zfs_list()

    if not zpool_info or not zfs_datasets:
        print(
            "Error: Could not retrieve ZFS pool or dataset information for validation."
        )
        return False

    total_pool_size_zpool = None
    if zpool_info["pools"]:
        total_pool_size_zpool = zpool_info[
            "pools"
        ][
            0
        ][
            "allocatable"
        ]  # Using allocatable for validation from first pool (assuming rpool is listed first or similar)

    total_used_space_zfs = 0
    total_available_space_zfs = 0

    print("\nZFS Datasets Summary:")
    for dataset in zfs_datasets:
        print(f"  Dataset: {dataset['name']}")
        print(f"    Used:      {dataset['used']}")
        print(f"    Available: {dataset['available']}")
        print(f"    Mountpoint:{dataset['mountpoint']}")
        try:  # Handle potential errors during conversion, like "-" for Available space in snapshots
            used_bytes = convert_size_to_bytes(dataset["used"])
        except ValueError:
            used_bytes = 0  # Treat as 0 if conversion fails (e.g., for "N/A" or "-")
        total_used_space_zfs += used_bytes
        try:
            available_bytes = convert_size_to_bytes(dataset["available"])
        except ValueError:
            available_bytes = 0  # Treat as 0 if conversion fails
        total_available_space_zfs += available_bytes

    print("\n--- Summary ---")
    print(
        f"Total Pool Size (zpool):  {bytes_to_human_readable(total_pool_size_zpool) if total_pool_size_zpool is not None else 'N/A (parsing issue)'}"
    )
    print(
        f"Total Used Space (datasets): {bytes_to_human_readable(total_used_space_zfs)}"
    )
    print(
        f"Total Available Space (datasets): {bytes_to_human_readable(total_available_space_zfs)}"
    )

    # Expected size of a 2TB drive in binary is approximately 1.81 TiB.
    # We will check if the allocatable space is reasonably close to this.
    expected_size_bytes_lower = 1.7 * (1024**4)  # 1.7 TiB in bytes (lower bound)
    expected_size_bytes_upper = 2.0 * (
        1024**4
    )  # 2.0 TiB in bytes (upper bound - slightly generous)

    if (
        total_pool_size_zpool is not None
        and total_pool_size_zpool > expected_size_bytes_lower
    ):  # A more lenient check to accommodate some overhead
        print("\n--- Expansion Validation Successful (Preliminary) ---")
        print(
            f"The reported pool size ({bytes_to_human_readable(total_pool_size_zpool)}) is within the expected range for a 2TB drive."
        )
        print(
            "Please check 'zpool status' and 'zfs list' manually for a detailed confirmation."
        )
        return True
    else:
        print("\n--- Expansion Validation Failed (Preliminary) ---")
        print(
            f"The reported pool size ({bytes_to_human_readable(total_pool_size_zpool) if total_pool_size_zpool is not None else 'N/A'}) is smaller than expected for a 2TB drive or parsing failed."
        )
        print(
            "Further investigation is needed. Check 'zpool status' for errors and consider manual partition resizing if necessary."
        )
        return False


def convert_size_to_bytes(size_str):
    """Converts human-readable size string (e.g., '100K', '1G', '200M') to bytes."""
    size_str = size_str.upper()
    if size_str == "0B":  # Handle "0B" case explicitly
        return 0
    units = {"K": 1024**1, "M": 1024**2, "G": 1024**3, "T": 1024**4, "P": 1024**5}
    if size_str[-1] in units:
        unit = size_str[-1]
        value = float(size_str[:-1])
        return int(value * units[unit])
    else:
        return int(size_str)  # Assumes bytes if no unit


def bytes_to_human_readable(bytes_val):
    """Converts bytes to human-readable format (e.g., KB, MB, GB, TB)."""
    if bytes_val is None:
        return "N/A"  # Handle None case
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(bytes_val)
    for unit in units:
        if abs(size) < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} {units[-1]}"


def main():
    print("--- ZFS Pool Expansion Script ---")

    pool_status = get_zpool_status()
    if not pool_status or not pool_status["pools"]:
        print(
            "Error: Could not retrieve ZFS pool status. Please ensure ZFS is properly configured."
        )
        return

    pools = pool_status["pools"]
    if len(pools) != 2:  # Expecting bpool and rpool based on user output
        print(
            "Warning: Script expects 'bpool' and 'rpool'. Found different pool configuration. Proceed with caution."
        )

    pool_device_paths = {}  # Dictionary to store pool and device path

    for pool in pools:
        vdevs = pool["vdevs"]
        if vdevs and vdevs[0]["type"] == "disk":  # Assuming simple disk vdevs
            device_path = vdevs[0]["path"]
            pool_name = pool["name"]
            pool_device_paths[pool_name] = device_path  # Store in dictionary
        else:
            print(
                f"Warning: Could not determine device path for pool '{pool['name']}'. Script may not be able to expand this pool."
            )

    print("\nDetected ZFS Pools and Devices:")
    for (
        pool_name,
        device_path,
    ) in pool_device_paths.items():  # Iterate through dictionary
        print(f"  Pool: {pool_name}, Device: {device_path}")

    print("\n--- Starting ZFS Pool Expansion Process ---")

    for (
        pool_name,
        device_path,
    ) in pool_device_paths.items():  # Iterate through dictionary
        expand_zpool(pool_name, device_path)  # Pass device_path to expand_zpool

    print("\n--- Expansion Process Completed ---")

    validate_expansion()

    print("\n--- Script Finished ---")


if __name__ == "__main__":
    if os.geteuid() != 0:
        print("Error: This script requires root privileges. Please run with sudo.")
        exit(1)
    main()
