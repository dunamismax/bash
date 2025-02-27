#!/usr/bin/env python3
"""
Simplified File Operations Toolkit

A basic command-line tool for file management and system operations.

Usage:
    python file_toolkit.py [operation] [arguments]

Operations:
    copy    - Copy files or directories
    move    - Move files or directories
    delete  - Delete files or directories
    find    - Search for files
    compress- Compress files
    checksum- Calculate file checksums
    du      - Disk usage analysis
"""

import argparse
import os
import shutil
import sys
import tarfile
import hashlib
import datetime
import stat


def copy_item(src, dest):
    """
    Copy a file or directory.

    Args:
        src (str): Source file or directory path
        dest (str): Destination file or directory path
    """
    try:
        if os.path.isdir(src):
            shutil.copytree(src, dest)
        else:
            shutil.copy2(src, dest)
        print(f"Successfully copied {src} to {dest}")
    except Exception as e:
        print(f"Error copying {src}: {e}", file=sys.stderr)
        sys.exit(1)


def move_item(src, dest):
    """
    Move a file or directory.

    Args:
        src (str): Source file or directory path
        dest (str): Destination file or directory path
    """
    try:
        shutil.move(src, dest)
        print(f"Successfully moved {src} to {dest}")
    except Exception as e:
        print(f"Error moving {src}: {e}", file=sys.stderr)
        sys.exit(1)


def delete_item(path):
    """
    Delete a file or directory.

    Args:
        path (str): Path of file or directory to delete
    """
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        print(f"Successfully deleted {path}")
    except Exception as e:
        print(f"Error deleting {path}: {e}", file=sys.stderr)
        sys.exit(1)


def find_files(directory, pattern):
    """
    Find files matching a pattern in a directory.

    Args:
        directory (str): Directory to search in
        pattern (str): File name pattern to search for
    """
    matches = []
    for root, _, files in os.walk(directory):
        for filename in files:
            if pattern == "*" or pattern == filename or pattern in filename:
                matches.append(os.path.join(root, filename))

    if matches:
        print("Matching files:")
        for match in matches:
            print(match)
    else:
        print("No files found matching the pattern.")


def compress_files(src, dest):
    """
    Compress files or directories using tar.

    Args:
        src (str): Source file or directory to compress
        dest (str): Destination tar file path
    """
    try:
        with tarfile.open(dest, "w:gz") as tar:
            tar.add(src, arcname=os.path.basename(src))
        print(f"Successfully compressed {src} to {dest}")
    except Exception as e:
        print(f"Error compressing {src}: {e}", file=sys.stderr)
        sys.exit(1)


def calculate_checksum(path, algorithm="md5"):
    """
    Calculate file checksum.

    Args:
        path (str): Path to the file
        algorithm (str): Hash algorithm to use (md5, sha1, sha256)
    """
    try:
        hash_func = hashlib.new(algorithm)
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_func.update(chunk)
        print(f"{algorithm.upper()} Checksum: {hash_func.hexdigest()}")
    except Exception as e:
        print(f"Error calculating checksum: {e}", file=sys.stderr)
        sys.exit(1)


def disk_usage(directory):
    """
    Analyze disk usage in a directory.

    Args:
        directory (str): Directory to analyze
    """

    def sizeof_fmt(num):
        """Convert bytes to human-readable format."""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if abs(num) < 1024.0:
                return f"{num:3.1f} {unit}"
            num /= 1024.0
        return f"{num:3.1f} PB"

    total_size = 0
    file_count = 0
    dir_count = 0
    recently_accessed = []
    rarely_accessed = []
    now = datetime.datetime.now()

    try:
        for root, dirs, files in os.walk(directory):
            dir_count += len(dirs)

            for file in files:
                file_path = os.path.join(root, file)
                try:
                    file_stat = os.stat(file_path)
                    file_count += 1
                    total_size += file_stat.st_size

                    # Check last access time
                    last_access = datetime.datetime.fromtimestamp(file_stat.st_atime)
                    days_since_access = (now - last_access).days

                    if days_since_access <= 30:
                        recently_accessed.append((file_path, days_since_access))
                    else:
                        rarely_accessed.append((file_path, days_since_access))

                except Exception as e:
                    print(f"Could not process {file_path}: {e}", file=sys.stderr)

        # Print summary
        print("Disk Usage Summary:")
        print(f"Total Size: {sizeof_fmt(total_size)}")
        print(f"Total Directories: {dir_count}")
        print(f"Total Files: {file_count}")

        print("\nRecently Accessed Files (last 30 days):")
        for file, days in sorted(recently_accessed, key=lambda x: x[1]):
            print(f"  {file} (Last accessed {days} days ago)")

        print("\nRarely Accessed Files (over 30 days):")
        for file, days in sorted(rarely_accessed, key=lambda x: x[1], reverse=True):
            print(f"  {file} (Last accessed {days} days ago)")

    except Exception as e:
        print(f"Error analyzing disk usage: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """
    Main entry point for the file toolkit.
    """
    parser = argparse.ArgumentParser(description="Simplified File Operations Toolkit")
    parser.add_argument(
        "operation",
        choices=["copy", "move", "delete", "find", "compress", "checksum", "du"],
        help="Operation to perform",
    )
    parser.add_argument("paths", nargs="+", help="Paths for the operation")

    # Optional arguments
    parser.add_argument(
        "-p", "--pattern", default="*", help="Pattern for find operation (default: *)"
    )
    parser.add_argument(
        "-a",
        "--algorithm",
        default="md5",
        choices=["md5", "sha1", "sha256"],
        help="Checksum algorithm (default: md5)",
    )

    args = parser.parse_args()

    try:
        if args.operation == "copy":
            if len(args.paths) < 2:
                raise ValueError("Copy requires source and destination paths")
            copy_item(args.paths[0], args.paths[1])

        elif args.operation == "move":
            if len(args.paths) < 2:
                raise ValueError("Move requires source and destination paths")
            move_item(args.paths[0], args.paths[1])

        elif args.operation == "delete":
            for path in args.paths:
                delete_item(path)

        elif args.operation == "find":
            if len(args.paths) != 1:
                raise ValueError("Find requires exactly one directory path")
            find_files(args.paths[0], args.pattern)

        elif args.operation == "compress":
            if len(args.paths) < 2:
                raise ValueError("Compress requires source and destination paths")
            compress_files(args.paths[0], args.paths[1])

        elif args.operation == "checksum":
            for path in args.paths:
                calculate_checksum(path, args.algorithm)

        elif args.operation == "du":
            for path in args.paths:
                disk_usage(path)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
