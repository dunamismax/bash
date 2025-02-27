#!/usr/bin/env python3
"""
Unified Restore Script (B2 CLI Version with Recursive Scan)

This script uses the B2 CLI tool (with a full path) to scan the sawyer-backups bucket for all restic repositories,
even if they are nested in subdirectories. It displays a numbered list of available backups and prompts the user
to select one or more repositories to restore (multiple selections are allowed via space-separated numbers).
Each selected repository is restored into its own subfolder under the restore base directory.

Note: Run this script with root privileges.
"""

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

#####################################
# B2 and Restic Configuration
#####################################

# Full path to the B2 CLI tool. Update this path if your installation is elsewhere.
B2_CLI = "/home/sawyer/.local/bin/b2"

# ------------------------------------------------------------------------------
# B2 Configuration
# ------------------------------------------------------------------------------
B2_ACCOUNT_ID = "12345678"
B2_ACCOUNT_KEY = "12345678"
B2_BUCKET = "sawyer-backups"
RESTIC_PASSWORD = "12345678"

# Restore base directory (each repo will restore into a subfolder here)
RESTORE_BASE: Path = Path("/home/sawyer/restic_restore")

# Retry settings for restic commands
MAX_RETRIES: int = 3
RETRY_DELAY: int = 5  # seconds

# Logging configuration
LOG_FILE: str = "/var/log/unified_restore.log"

#####################################
# Nord-Themed ANSI Colors for CLI Output
#####################################


class Colors:
    HEADER = "\033[38;5;81m"  # Nord9
    GREEN = "\033[38;5;82m"  # Nord14
    YELLOW = "\033[38;5;226m"  # Nord13
    RED = "\033[38;5;196m"  # Nord11
    BLUE = "\033[38;5;39m"  # Nord8
    BOLD = "\033[1m"
    ENDC = "\033[0m"


def print_header(message: str) -> None:
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 80}")
    print(message.center(80))
    print(f"{'=' * 80}{Colors.ENDC}\n")


#####################################
# Logging Setup
#####################################


def setup_logging() -> None:
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_FILE, mode="a"),
        ],
    )


#####################################
# Signal Handling
#####################################


def signal_handler(signum: int, frame: Any) -> None:
    logging.error(
        f"{Colors.RED}Script interrupted by {signal.Signals(signum).name}.{Colors.ENDC}"
    )
    sys.exit(1)


for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)

#####################################
# Utility Functions
#####################################


def check_root() -> None:
    if os.geteuid() != 0:
        logging.error(
            f"{Colors.RED}This script must be run with root privileges.{Colors.ENDC}"
        )
        sys.exit(1)


def run_restic(
    repo: str, args: List[str], capture_output: bool = False
) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["RESTIC_PASSWORD"] = RESTIC_PASSWORD
    if repo.startswith("b2:"):
        env["B2_ACCOUNT_ID"] = B2_ACCOUNT_ID
        env["B2_ACCOUNT_KEY"] = B2_ACCOUNT_KEY

    cmd: List[str] = ["restic", "--repo", repo] + args
    logging.info(f"Running command: {' '.join(cmd)}")
    retries = 0

    while retries <= MAX_RETRIES:
        try:
            result = subprocess.run(
                cmd,
                env=env,
                check=True,
                stdout=subprocess.PIPE if capture_output else None,
                stderr=subprocess.PIPE if capture_output else None,
                text=True,
            )
            return result
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr or str(e)
            if "timeout" in error_msg.lower() or "connection" in error_msg.lower():
                retries += 1
                delay = RETRY_DELAY * (2 ** (retries - 1))
                logging.warning(
                    f"{Colors.YELLOW}Transient error; retrying in {delay} seconds (attempt {retries}).{Colors.ENDC}"
                )
                time.sleep(delay)
            else:
                logging.error(
                    f"{Colors.RED}Restic command failed: {error_msg}{Colors.ENDC}"
                )
                raise
    raise RuntimeError("Max retries exceeded in run_restic")


def get_latest_snapshot(repo: str) -> Optional[str]:
    try:
        result = run_restic(repo, ["snapshots", "--json"], capture_output=True)
        snapshots = json.loads(result.stdout) if result.stdout else []
        if not snapshots:
            logging.warning(
                f"{Colors.YELLOW}No snapshots found in repository: {repo}{Colors.ENDC}"
            )
            return None
        latest = max(snapshots, key=lambda s: s.get("time", ""))
        snap_id = latest.get("id")
        logging.info(f"Latest snapshot for {repo} is {snap_id}")
        return snap_id
    except Exception as e:
        logging.error(
            f"{Colors.RED}Error retrieving snapshots for {repo}: {e}{Colors.ENDC}"
        )
        return None


#####################################
# Scanning for Repositories using B2 CLI
#####################################


def scan_for_repos() -> Dict[int, Tuple[str, str]]:
    """
    Recursively scan the B2 bucket for restic repositories.
    A repository is identified by the presence of a 'config' file in any subdirectory.

    Returns:
        Dictionary mapping menu numbers to (repo_name, repo_path).
        The repo_path is formatted as "b2:{B2_BUCKET}:{repository_folder}".
    """
    repos: Dict[int, Tuple[str, str]] = {}
    seen: set = set()
    try:
        # Use the full path to the B2 CLI tool with recursive listing.
        cmd = [B2_CLI, "ls", B2_BUCKET, "--recursive"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        for line in result.stdout.splitlines():
            line = line.strip()
            parts = line.split("/")
            # Check if the last segment of the path is "config"
            if parts[-1] == "config" and len(parts) > 1:
                repo_folder = "/".join(parts[:-1])
                if repo_folder in seen:
                    continue
                seen.add(repo_folder)
                # Use the last folder name as the repository name
                repo_name = repo_folder.split("/")[-1]
                repo_path = f"b2:{B2_BUCKET}:{repo_folder}"
                repos[len(repos) + 1] = (repo_name, repo_path)
    except subprocess.CalledProcessError as e:
        logging.error(
            f"{Colors.RED}Error scanning B2 bucket: {e.stderr or str(e)}{Colors.ENDC}"
        )
    return repos


#####################################
# Restore Operation
#####################################


def restore_repo(repo: str, target: Path) -> bool:
    snap_id = get_latest_snapshot(repo)
    if not snap_id:
        logging.error(
            f"{Colors.RED}Skipping restore for {repo} - no snapshot found.{Colors.ENDC}"
        )
        return False

    target.mkdir(parents=True, exist_ok=True)
    logging.info(
        f"{Colors.BLUE}Restoring snapshot {snap_id} from {repo} into {target}...{Colors.ENDC}"
    )
    try:
        run_restic(
            repo, ["restore", snap_id, "--target", str(target)], capture_output=True
        )
        if not any(target.iterdir()):
            logging.error(
                f"{Colors.RED}Restore failed: {target} is empty after restore.{Colors.ENDC}"
            )
            return False
        logging.info(
            f"{Colors.GREEN}Successfully restored {repo} into {target}.{Colors.ENDC}"
        )
        return True
    except Exception as e:
        logging.error(f"{Colors.RED}Restore failed for {repo}: {e}{Colors.ENDC}")
        return False


#####################################
# CLI Argument Parsing
#####################################


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Unified Restore Script: Recursively scan B2 for restic repositories and restore selected backups."
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Restore a specific repository by providing its repo path via --repo (skips scanning menu).",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default="",
        help="Specify a single restic repository path to restore (e.g., 'b2:sawyer-backups:some/repo').",
    )
    return parser.parse_args()


#####################################
# Main Function
#####################################


def main() -> None:
    setup_logging()
    check_root()
    print_header("Unified Restore Script")
    logging.info(f"Restore started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    args = parse_arguments()

    # In non-interactive mode, use provided repo only.
    if args.non_interactive and args.repo:
        selected_repos = {1: ("CustomRepo", args.repo)}
    else:
        available_repos = scan_for_repos()
        if not available_repos:
            logging.error(
                f"{Colors.RED}No restic repositories found in bucket {B2_BUCKET}.{Colors.ENDC}"
            )
            sys.exit(1)
        print(f"{Colors.BOLD}Available Restic Repositories:{Colors.ENDC}")
        for num, (repo_name, repo_path) in available_repos.items():
            print(f"  {num}. {repo_name}  [{repo_path}]")
        selection = input(
            "\nEnter the numbers of the repositories to restore (separated by spaces): "
        ).strip()
        if not selection:
            logging.error(f"{Colors.RED}No selection made. Exiting.{Colors.ENDC}")
            sys.exit(1)
        try:
            choices = [int(num) for num in selection.split()]
        except ValueError:
            logging.error(
                f"{Colors.RED}Invalid input. Please enter valid numbers separated by spaces.{Colors.ENDC}"
            )
            sys.exit(1)
        selected_repos = {
            num: available_repos[num] for num in choices if num in available_repos
        }
        if not selected_repos:
            logging.error(
                f"{Colors.RED}No valid repositories selected. Exiting.{Colors.ENDC}"
            )
            sys.exit(1)

    start_time = time.time()
    results: Dict[str, bool] = {}
    for _, (repo_name, repo_path) in selected_repos.items():
        target_dir = RESTORE_BASE / repo_name
        logging.info(
            f"Restoring repository '{repo_name}' from {repo_path} into {target_dir}..."
        )
        result = restore_repo(repo_path, target_dir)
        results[repo_name] = result

    total_time = time.time() - start_time
    print_header("Restore Summary")
    for repo_name, success in results.items():
        status = (
            f"{Colors.GREEN}SUCCESS{Colors.ENDC}"
            if success
            else f"{Colors.RED}FAILED{Colors.ENDC}"
        )
        logging.info(f"{repo_name} restore: {status}")
        print(f"{repo_name} restore: {status}")

    logging.info(f"Total restore time: {total_time:.2f} seconds")
    print(f"\nTotal restore time: {total_time:.2f} seconds")
    sys.exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error(f"{Colors.RED}Unhandled exception: {e}{Colors.ENDC}")
        sys.exit(1)
