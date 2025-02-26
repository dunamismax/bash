#!/usr/bin/env python3
"""
Advanced File & Security Operations Toolkit
---------------------------------------------
Description:
  An advanced file encryption, decryption, compression, and file management toolkit
  for Ubuntu. This interactive tool offers a Nord-themed menu with rich integration for:
    - File copy, move, delete, and advanced search
    - Multicore compression/decompression (via pigz)
    - Password-based encryption/decryption (via OpenSSL)
    - Interactive PGP operations (key generation, message encryption/decryption,
      signing, and verification)
    - Checksum calculation (MD5/SHA256)

Usage:
  sudo ./file_toolkit.py

Author: Your Name | License: MIT | Version: 4.0.0
"""

import atexit
import getpass
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

# Global rich console instance for formatted output
console = Console()

# ------------------------------------------------------------------------------
# Environment Configuration
# ------------------------------------------------------------------------------
LOG_FILE = "/var/log/advanced_file_tool.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
DEFAULT_LOG_LEVEL = "INFO"

# ------------------------------------------------------------------------------
# Nord Color Palette (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0 = "\033[38;2;46;52;64m"  # Polar Night (dark)
NORD1 = "\033[38;2;59;66;82m"  # Polar Night (darker than NORD0)
NORD2 = "\033[38;2;67;76;94m"  # Polar Night (darker than NORD1)
NORD3 = "\033[38;2;76;86;106m"  # Polar Night (darker than NORD2)
NORD4 = "\033[38;2;216;222;233m"  # Snow Storm (lightest)
NORD5 = "\033[38;2;229;233;240m"  # Snow Storm (middle)
NORD6 = "\033[38;2;236;239;244m"  # Snow Storm (darkest)
NORD7 = "\033[38;2;143;188;187m"  # Frost (teal)
NORD8 = "\033[38;2;136;192;208m"  # Frost (light blue)
NORD9 = "\033[38;2;129;161;193m"  # Bluish (DEBUG)
NORD10 = "\033[38;2;94;129;172m"  # Accent Blue (section headers)
NORD11 = "\033[38;2;191;97;106m"  # Reddish (ERROR/CRITICAL)
NORD12 = "\033[38;2;208;135;112m"  # Aurora (orange)
NORD13 = "\033[38;2;235;203;139m"  # Yellowish (WARN)
NORD14 = "\033[38;2;163;190;140m"  # Greenish (INFO)
NORD15 = "\033[38;2;180;142;173m"  # Purple
NC = "\033[0m"  # Reset / No Color


# ------------------------------------------------------------------------------
# CUSTOM LOGGING
# ------------------------------------------------------------------------------
class NordColorFormatter(logging.Formatter):
    """
    A custom logging formatter that applies the Nord color theme.
    """

    def __init__(self, fmt=None, datefmt=None, use_colors=True):
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors and not DISABLE_COLORS

    def format(self, record):
        msg = super().format(record)
        if not self.use_colors:
            return msg
        level = record.levelname
        if level == "DEBUG":
            return f"{NORD9}{msg}{NC}"
        elif level == "INFO":
            return f"{NORD14}{msg}{NC}"
        elif level == "WARNING":
            return f"{NORD13}{msg}{NC}"
        elif level in ("ERROR", "CRITICAL"):
            return f"{NORD11}{msg}{NC}"
        return msg


def setup_logging():
    """
    Set up logging with console and file handlers using the Nord color theme.
    """
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    console_formatter = NordColorFormatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    file_formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    try:
        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logger.warning(f"Failed to set up log file {LOG_FILE}: {e}")
        logger.warning("Continuing with console logging only")
    return logger


def print_section(title: str):
    """
    Print a Nord-themed section header.
    """
    border = "─" * 60
    if not DISABLE_COLORS:
        logging.info(f"{NORD10}{border}{NC}")
        logging.info(f"{NORD10}  {title}{NC}")
        logging.info(f"{NORD10}{border}{NC}")
    else:
        logging.info(border)
        logging.info(f"  {title}")
        logging.info(border)


# ------------------------------------------------------------------------------
# SIGNAL HANDLING & CLEANUP
# ------------------------------------------------------------------------------
def signal_handler(signum, frame):
    """
    Handle termination signals gracefully.
    """
    sig_name = (
        signal.Signals(signum).name
        if hasattr(signal, "Signals")
        else f"signal {signum}"
    )
    logging.error(f"Script interrupted by {sig_name}.")
    try:
        cleanup()
    except Exception as e:
        logging.error(f"Error during cleanup after signal: {e}")
    if signum == signal.SIGINT:
        sys.exit(130)
    elif signum == signal.SIGTERM:
        sys.exit(143)
    else:
        sys.exit(128 + signum)


for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, signal_handler)


def cleanup():
    """
    Perform cleanup tasks before exiting.
    """
    logging.info("Performing cleanup tasks before exit.")
    # Additional cleanup tasks can be added here


atexit.register(cleanup)


# ------------------------------------------------------------------------------
# DEPENDENCY CHECKING & PRIVILEGE VALIDATION
# ------------------------------------------------------------------------------
def check_dependencies():
    """
    Check for required system commands.
    """
    required_commands = ["find", "tar", "pigz", "openssl", "gpg", "md5sum", "sha256sum"]
    missing_commands = [cmd for cmd in required_commands if not shutil.which(cmd)]
    if missing_commands:
        missing_list = ", ".join(missing_commands)
        logging.error(f"Missing required commands: {missing_list}")
        console.print(
            f"{NORD11}The following required commands are missing: {missing_list}{NC}"
        )
        console.print(f"{NORD11}Please install them and try again.{NC}")
        sys.exit(1)


def check_root():
    """
    Ensure the script is executed with root privileges.
    """
    if os.geteuid() != 0:
        logging.error("This script must be run as root.")
        sys.exit(1)
    logging.debug("Running with root privileges.")


# ------------------------------------------------------------------------------
# UI HELPER FUNCTIONS
# ------------------------------------------------------------------------------
def print_header():
    """
    Clear the screen and print the application header.
    """
    os.system("clear")
    border = "═" * 60
    console.print(f"{NORD8}{border}{NC}")
    console.print(f"{NORD8}  Advanced File & Security Operations Tool {NORD10}v4.0{NC}")
    console.print(f"{NORD8}{border}{NC}")


def print_divider():
    """
    Print a visual divider.
    """
    console.print(f"{NORD8}{'─' * 60}{NC}")


def prompt_enter():
    """
    Wait for the user to press Enter.
    """
    input(f"{NORD13}Press Enter to continue...{NC}")


# ------------------------------------------------------------------------------
# PROGRESS HELPER (using rich)
# ------------------------------------------------------------------------------
def run_with_progress(description: str, func, *args, **kwargs):
    """
    Execute a blocking function in a background thread while displaying a progress spinner.
    """
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            transient=True,
        ) as progress:
            task = progress.add_task(description, total=None)
            while not future.done():
                time.sleep(0.1)
                progress.refresh()
            return future.result()


# ------------------------------------------------------------------------------
# FILE OPERATIONS FUNCTIONS
# ------------------------------------------------------------------------------
def file_copy():
    """
    Copy a file or directory to a destination.
    """
    print_section("File Copy Operation")
    logging.info("Initiating file copy operation.")
    src = input(f"{NORD13}Enter source file/directory: {NC}").strip()
    dest = input(f"{NORD13}Enter destination path: {NC}").strip()
    if not os.path.exists(src):
        logging.error(f"Source '{src}' does not exist.")
        console.print(f"[bold red]Error: Source '{src}' does not exist.[/bold red]")
        return

    try:

        def copy_operation():
            if os.path.isdir(src):
                shutil.copytree(src, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dest)

        run_with_progress("Copying...", copy_operation)
        logging.info(f"Copied '{src}' to '{dest}' successfully.")
        console.print(f"[bold green]Copy completed successfully.[/bold green]")
    except Exception as e:
        logging.error(f"Copy failed: {e}")
        console.print(f"[bold red]Error: Copy failed - {e}[/bold red]")


def file_move():
    """
    Move a file or directory to a destination.
    """
    print_section("File Move Operation")
    logging.info("Initiating file move operation.")
    src = input(f"{NORD13}Enter source file/directory: {NC}").strip()
    dest = input(f"{NORD13}Enter destination path: {NC}").strip()
    if not os.path.exists(src):
        logging.error(f"Source '{src}' does not exist.")
        console.print(f"[bold red]Error: Source '{src}' does not exist.[/bold red]")
        return

    try:

        def move_operation():
            shutil.move(src, dest)

        run_with_progress("Moving...", move_operation)
        logging.info(f"Moved '{src}' to '{dest}' successfully.")
        console.print(f"[bold green]Move completed successfully.[/bold green]")
    except Exception as e:
        logging.error(f"Move failed: {e}")
        console.print(f"[bold red]Error: Move failed - {e}[/bold red]")


def file_delete():
    """
    Delete a file or directory.
    """
    print_section("File Deletion Operation")
    logging.info("Initiating file deletion operation.")
    target = input(f"{NORD13}Enter file/directory to delete: {NC}").strip()
    if not os.path.exists(target):
        logging.error(f"Target '{target}' does not exist.")
        console.print(f"[bold red]Error: Target '{target}' does not exist.[/bold red]")
        return

    confirm = (
        input(f"{NORD13}Are you sure you want to delete '{target}'? (y/n): {NC}")
        .strip()
        .lower()
    )
    if confirm.startswith("y"):
        try:

            def delete_operation():
                if os.path.isdir(target):
                    shutil.rmtree(target)
                else:
                    os.remove(target)

            run_with_progress("Deleting...", delete_operation)
            logging.info(f"Deleted '{target}' successfully.")
            console.print(f"[bold green]Deletion completed successfully.[/bold green]")
        except Exception as e:
            logging.error(f"Deletion failed: {e}")
            console.print(f"[bold red]Error: Deletion failed - {e}[/bold red]")
    else:
        logging.warning("Deletion cancelled by user.")
        console.print(f"[bold yellow]Deletion cancelled.[/bold yellow]")


def file_search():
    """
    Search for files matching a pattern in a directory.
    """
    print_section("Advanced File Search")
    logging.info("Initiating advanced file search.")
    search_dir = input(f"{NORD13}Enter directory to search in: {NC}").strip()
    pattern = input(f"{NORD13}Enter filename pattern (e.g., *.txt): {NC}").strip()
    if not os.path.isdir(search_dir):
        logging.error(f"Directory '{search_dir}' does not exist.")
        console.print(
            f"[bold red]Error: Directory '{search_dir}' does not exist.[/bold red]"
        )
        return

    console.print(f"[bold green]Search results:[/bold green]")
    try:

        def search_operation():
            result = subprocess.run(
                ["find", search_dir, "-type", "f", "-name", pattern],
                check=True,
                text=True,
                capture_output=True,
            )
            return result.stdout.strip()

        output = run_with_progress("Searching...", search_operation)
        if output:
            console.print(output)
        else:
            console.print(
                f"[bold yellow]No files found matching the pattern.[/bold yellow]"
            )
        logging.info(f"Search completed in '{search_dir}' for pattern '{pattern}'.")
    except subprocess.CalledProcessError as e:
        logging.error(f"File search failed: {e}")
        console.print(f"[bold red]Error: File search failed - {e.stderr}[/bold red]")


# ------------------------------------------------------------------------------
# COMPRESSION / DECOMPRESSION FUNCTIONS (using pigz)
# ------------------------------------------------------------------------------
def compress_file():
    """
    Compress a file or directory using tar and pigz.
    """
    print_section("File Compression")
    logging.info("Initiating compression operation.")
    target = input(f"{NORD13}Enter file or directory to compress: {NC}").strip()
    if not os.path.exists(target):
        logging.error(f"Target '{target}' does not exist.")
        console.print(f"[bold red]Error: Target '{target}' does not exist.[/bold red]")
        return

    outfile = input(
        f"{NORD13}Enter output archive name (e.g., archive.tar.gz): {NC}"
    ).strip()
    cmd = f"tar -cf - {target} | pigz > {outfile}"
    try:
        run_with_progress("Compressing...", subprocess.run, cmd, shell=True, check=True)
        logging.info(f"Compressed '{target}' to '{outfile}' successfully.")
        console.print(f"[bold green]Compression completed successfully.[/bold green]")
    except subprocess.CalledProcessError as e:
        logging.error(f"Compression failed: {e}")
        console.print(f"[bold red]Error: Compression failed - {e}[/bold red]")


def decompress_file():
    """
    Decompress a tar.gz file using pigz and tar.
    """
    print_section("File Decompression")
    logging.info("Initiating decompression operation.")
    infile = input(
        f"{NORD13}Enter compressed file (e.g., archive.tar.gz): {NC}"
    ).strip()
    if not os.path.isfile(infile):
        logging.error(f"File '{infile}' does not exist.")
        console.print(f"[bold red]Error: File '{infile}' does not exist.[/bold red]")
        return

    outdir = input(f"{NORD13}Enter output directory: {NC}").strip()
    try:
        os.makedirs(outdir, exist_ok=True)
    except Exception as e:
        logging.error(f"Failed to create output directory: {e}")
        console.print(
            f"[bold red]Error: Failed to create output directory - {e}[/bold red]"
        )
        return

    cmd = f"pigz -dc {infile} | tar -xf - -C {outdir}"
    try:
        run_with_progress(
            "Decompressing...", subprocess.run, cmd, shell=True, check=True
        )
        logging.info(f"Decompressed '{infile}' to '{outdir}' successfully.")
        console.print(f"[bold green]Decompression completed successfully.[/bold green]")
    except subprocess.CalledProcessError as e:
        logging.error(f"Decompression failed: {e}")
        console.print(f"[bold red]Error: Decompression failed - {e}[/bold red]")


# ------------------------------------------------------------------------------
# FILE ENCRYPTION / DECRYPTION (using OpenSSL)
# ------------------------------------------------------------------------------
def encrypt_file():
    """
    Encrypt a file using OpenSSL (AES-256-CBC).
    """
    print_section("File Encryption")
    logging.info("Initiating file encryption.")
    infile = input(f"{NORD13}Enter file to encrypt: {NC}").strip()
    if not os.path.isfile(infile):
        logging.error(f"File '{infile}' does not exist.")
        console.print(f"[bold red]Error: File '{infile}' does not exist.[/bold red]")
        return

    outfile = input(f"{NORD13}Enter output encrypted file name: {NC}").strip()
    password = getpass.getpass(f"{NORD13}Enter password: {NC}")
    cmd = [
        "openssl",
        "enc",
        "-aes-256-cbc",
        "-salt",
        "-in",
        infile,
        "-out",
        outfile,
        "-pass",
        f"pass:{password}",
    ]
    try:
        run_with_progress(
            "Encrypting...", subprocess.run, cmd, check=True, capture_output=True
        )
        logging.info(f"Encrypted '{infile}' to '{outfile}' successfully.")
        console.print(f"[bold green]File encrypted successfully.[/bold green]")
    except subprocess.CalledProcessError as e:
        logging.error(f"Encryption failed: {e}")
        err = e.stderr.decode() if e.stderr else e
        console.print(f"[bold red]Error: Encryption failed - {err}[/bold red]")


def decrypt_file():
    """
    Decrypt a file using OpenSSL (AES-256-CBC).
    """
    print_section("File Decryption")
    logging.info("Initiating file decryption.")
    infile = input(f"{NORD13}Enter file to decrypt: {NC}").strip()
    if not os.path.isfile(infile):
        logging.error(f"File '{infile}' does not exist.")
        console.print(f"[bold red]Error: File '{infile}' does not exist.[/bold red]")
        return

    outfile = input(f"{NORD13}Enter output decrypted file name: {NC}").strip()
    password = getpass.getpass(f"{NORD13}Enter password: {NC}")
    cmd = [
        "openssl",
        "enc",
        "-d",
        "-aes-256-cbc",
        "-in",
        infile,
        "-out",
        outfile,
        "-pass",
        f"pass:{password}",
    ]
    try:
        run_with_progress(
            "Decrypting...", subprocess.run, cmd, check=True, capture_output=True
        )
        logging.info(f"Decrypted '{infile}' to '{outfile}' successfully.")
        console.print(f"[bold green]File decrypted successfully.[/bold green]")
    except subprocess.CalledProcessError as e:
        logging.error(f"Decryption failed: {e}")
        err = e.stderr.decode() if e.stderr else e
        console.print(f"[bold red]Error: Decryption failed - {err}[/bold red]")
        console.print(
            f"[bold yellow]Hint: Check if the password is correct.[/bold yellow]"
        )


# ------------------------------------------------------------------------------
# PGP OPERATIONS (using gpg)
# ------------------------------------------------------------------------------
def pgp_create_key():
    """
    Create a new PGP key pair using GPG.
    """
    print_section("PGP Key Generation")
    logging.info("Starting interactive PGP key generation.")
    console.print(
        f"[bold cyan]This will launch the interactive GPG key generation wizard. Follow the prompts to create your key.[/bold cyan]"
    )
    time.sleep(1)
    try:
        run_with_progress(
            "Generating PGP key...", subprocess.run, ["gpg", "--gen-key"], check=True
        )
        logging.info("PGP key generation completed.")
        console.print(
            f"[bold green]PGP key generation completed successfully.[/bold green]"
        )
    except subprocess.CalledProcessError as e:
        logging.error(f"PGP key generation failed: {e}")
        console.print(f"[bold red]Error: PGP key generation failed - {e}[/bold red]")


def pgp_encrypt_message():
    """
    Encrypt a message using PGP.
    """
    print_section("PGP Message Encryption")
    logging.info("Initiating PGP message encryption.")
    recipient = input(f"{NORD13}Enter recipient's email or key ID: {NC}").strip()
    console.print(
        f"[bold green]Enter the message to encrypt. End input with a single '.' on a new line.[/bold green]"
    )
    lines = []
    while True:
        line = input()
        if line.strip() == ".":
            break
        lines.append(line)
    msg = "\n".join(lines)
    try:

        def encrypt_operation():
            proc = subprocess.run(
                ["gpg", "--encrypt", "--armor", "-r", recipient],
                input=msg,
                text=True,
                check=True,
                capture_output=True,
            )
            return proc.stdout

        encrypted_msg = run_with_progress("Encrypting message...", encrypt_operation)
        console.print(f"[bold green]Encrypted message:[/bold green]")
        console.print(encrypted_msg)
        logging.info("Message encrypted successfully.")
    except subprocess.CalledProcessError as e:
        logging.error(f"PGP encryption failed: {e}")
        err = e.stderr if e.stderr else e
        console.print(f"[bold red]Error: PGP encryption failed - {err}[/bold red]")


def pgp_decrypt_message():
    """
    Decrypt a PGP-encrypted message.
    """
    print_section("PGP Message Decryption")
    logging.info("Initiating PGP message decryption.")
    infile = input(
        f"{NORD13}Enter file containing the PGP encrypted message: {NC}"
    ).strip()
    if not os.path.isfile(infile):
        logging.error(f"File '{infile}' does not exist.")
        console.print(f"[bold red]Error: File '{infile}' does not exist.[/bold red]")
        return
    try:

        def decrypt_operation():
            proc = subprocess.run(
                ["gpg", "--decrypt", infile], check=True, text=True, capture_output=True
            )
            return proc.stdout

        decrypted_msg = run_with_progress("Decrypting message...", decrypt_operation)
        console.print(f"[bold green]Decrypted message:[/bold green]")
        console.print(decrypted_msg)
        logging.info("PGP decryption completed.")
    except subprocess.CalledProcessError as e:
        logging.error(f"PGP decryption failed: {e}")
        console.print(f"[bold red]Error: PGP decryption failed - {e}[/bold red]")


def pgp_sign_message():
    """
    Sign a message with your PGP key.
    """
    print_section("PGP Message Signing")
    logging.info("Initiating message signing with PGP.")
    console.print(
        f"[bold green]Enter the message to sign. End input with a single '.' on a new line.[/bold green]"
    )
    lines = []
    while True:
        line = input()
        if line.strip() == ".":
            break
        lines.append(line)
    msg = "\n".join(lines)
    try:

        def sign_operation():
            result = subprocess.run(
                ["gpg", "--clearsign"],
                input=msg,
                text=True,
                check=True,
                capture_output=True,
            )
            return result.stdout

        signed_msg = run_with_progress("Signing message...", sign_operation)
        console.print(f"[bold green]Signed message:[/bold green]")
        console.print(signed_msg)
        logging.info("Message signed successfully.")
    except subprocess.CalledProcessError as e:
        logging.error(f"PGP signing failed: {e}")
        err = e.stderr if e.stderr else e
        console.print(f"[bold red]Error: PGP signing failed - {err}[/bold red]")


def pgp_verify_signature():
    """
    Verify a PGP signature.
    """
    print_section("PGP Signature Verification")
    logging.info("Initiating PGP signature verification.")
    infile = input(f"{NORD13}Enter the signed file to verify: {NC}").strip()
    if not os.path.isfile(infile):
        logging.error(f"File '{infile}' does not exist.")
        console.print(f"[bold red]Error: File '{infile}' does not exist.[/bold red]")
        return
    try:

        def verify_operation():
            result = subprocess.run(
                ["gpg", "--verify", infile], check=True, text=True, capture_output=True
            )
            return result.stderr

        verification_output = run_with_progress(
            "Verifying signature...", verify_operation
        )
        console.print(f"[bold green]Verification result:[/bold green]")
        if verification_output:
            console.print(verification_output)
        logging.info("Signature verified successfully.")
        console.print(f"[bold green]Signature verification completed.[/bold green]")
    except subprocess.CalledProcessError as e:
        logging.error(f"Signature verification failed: {e}")
        console.print(f"[bold red]Error: Signature verification failed.[/bold red]")
        if e.stderr:
            console.print(e.stderr)


# ------------------------------------------------------------------------------
# ADDITIONAL TOOLS FUNCTIONS
# ------------------------------------------------------------------------------
def calculate_checksum():
    """
    Calculate MD5 or SHA256 checksum for a file.
    """
    print_section("Checksum Calculation")
    logging.info("Starting checksum calculation.")
    file_path = input(f"{NORD13}Enter file to calculate checksum: {NC}").strip()
    if not os.path.isfile(file_path):
        logging.error(f"File '{file_path}' does not exist.")
        console.print(f"[bold red]Error: File '{file_path}' does not exist.[/bold red]")
        return

    console.print(f"[bold green]Select checksum type:[/bold green]")
    console.print(f"[bold cyan][1][/bold cyan] MD5")
    console.print(f"[bold cyan][2][/bold cyan] SHA256")
    choice = input(f"{NORD13}Enter choice (1 or 2): {NC}").strip()

    if choice == "1":
        cmd = ["md5sum", file_path]
        checksum_type = "MD5"
    elif choice == "2":
        cmd = ["sha256sum", file_path]
        checksum_type = "SHA256"
    else:
        logging.warning("Invalid checksum type selection.")
        console.print(f"[bold yellow]Invalid selection.[/bold yellow]")
        return

    try:

        def checksum_operation():
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            return result.stdout

        output = run_with_progress("Calculating checksum...", checksum_operation)
        console.print(f"[bold green]{checksum_type} Checksum:[/bold green]")
        console.print(output)
        logging.info(f"Calculated {checksum_type} checksum for '{file_path}'.")
    except subprocess.CalledProcessError as e:
        logging.error(f"Checksum calculation failed: {e}")
        console.print(f"[bold red]Error: Checksum calculation failed - {e}[/bold red]")


# ------------------------------------------------------------------------------
# INTERACTIVE MENUS
# ------------------------------------------------------------------------------
def file_operations_menu():
    """
    Display the file operations menu.
    """
    while True:
        print_header()
        console.print(f"{NORD14}File Operations:{NC}")
        print_divider()
        console.print(f"{NORD8}[1]{NC} Copy File/Directory")
        console.print(f"{NORD8}[2]{NC} Move File/Directory")
        console.print(f"{NORD8}[3]{NC} Delete File/Directory")
        console.print(f"{NORD8}[4]{NC} Advanced Search")
        console.print(f"{NORD8}[0]{NC} Return to Main Menu")
        print_divider()
        choice = input(f"{NORD13}Enter your choice: {NC}").strip()
        if choice == "1":
            file_copy()
            prompt_enter()
        elif choice == "2":
            file_move()
            prompt_enter()
        elif choice == "3":
            file_delete()
            prompt_enter()
        elif choice == "4":
            file_search()
            prompt_enter()
        elif choice == "0":
            break
        else:
            console.print(f"{NORD12}Invalid selection.{NC}")
            time.sleep(1)


def compression_menu():
    """
    Display the compression/decompression menu.
    """
    while True:
        print_header()
        console.print(f"{NORD14}Compression / Decompression (using pigz):{NC}")
        print_divider()
        console.print(f"{NORD8}[1]{NC} Compress File/Directory")
        console.print(f"{NORD8}[2]{NC} Decompress File")
        console.print(f"{NORD8}[0]{NC} Return to Main Menu")
        print_divider()
        choice = input(f"{NORD13}Enter your choice: {NC}").strip()
        if choice == "1":
            compress_file()
            prompt_enter()
        elif choice == "2":
            decompress_file()
            prompt_enter()
        elif choice == "0":
            break
        else:
            console.print(f"{NORD12}Invalid selection.{NC}")
            time.sleep(1)


def encryption_menu():
    """
    Display the encryption/decryption menu.
    """
    while True:
        print_header()
        console.print(f"{NORD14}File Encryption / Decryption (Password-based):{NC}")
        print_divider()
        console.print(f"{NORD8}[1]{NC} Encrypt a File")
        console.print(f"{NORD8}[2]{NC} Decrypt a File")
        console.print(f"{NORD8}[0]{NC} Return to Main Menu")
        print_divider()
        choice = input(f"{NORD13}Enter your choice: {NC}").strip()
        if choice == "1":
            encrypt_file()
            prompt_enter()
        elif choice == "2":
            decrypt_file()
            prompt_enter()
        elif choice == "0":
            break
        else:
            console.print(f"{NORD12}Invalid selection.{NC}")
            time.sleep(1)


def pgp_menu():
    """
    Display the PGP operations menu.
    """
    while True:
        print_header()
        console.print(f"{NORD14}PGP Operations:{NC}")
        print_divider()
        console.print(f"{NORD8}[1]{NC} Create PGP Key")
        console.print(f"{NORD8}[2]{NC} Encrypt Message")
        console.print(f"{NORD8}[3]{NC} Decrypt Message")
        console.print(f"{NORD8}[4]{NC} Sign Message")
        console.print(f"{NORD8}[5]{NC} Verify Signature")
        console.print(f"{NORD8}[0]{NC} Return to Main Menu")
        print_divider()
        choice = input(f"{NORD13}Enter your choice: {NC}").strip()
        if choice == "1":
            pgp_create_key()
            prompt_enter()
        elif choice == "2":
            pgp_encrypt_message()
            prompt_enter()
        elif choice == "3":
            pgp_decrypt_message()
            prompt_enter()
        elif choice == "4":
            pgp_sign_message()
            prompt_enter()
        elif choice == "5":
            pgp_verify_signature()
            prompt_enter()
        elif choice == "0":
            break
        else:
            console.print(f"{NORD12}Invalid selection.{NC}")
            time.sleep(1)


def additional_menu():
    """
    Display the additional tools menu.
    """
    while True:
        print_header()
        console.print(f"{NORD14}Additional Tools:{NC}")
        print_divider()
        console.print(f"{NORD8}[1]{NC} Calculate File Checksum")
        console.print(f"{NORD8}[0]{NC} Return to Main Menu")
        print_divider()
        choice = input(f"{NORD13}Enter your choice: {NC}").strip()
        if choice == "1":
            calculate_checksum()
            prompt_enter()
        elif choice == "0":
            break
        else:
            console.print(f"{NORD12}Invalid selection.{NC}")
            time.sleep(1)


def main_menu():
    """
    Display the main menu.
    """
    while True:
        print_header()
        console.print(f"{NORD14}Main Menu:{NC}")
        print_divider()
        console.print(f"{NORD8}[1]{NC} File Operations")
        console.print(f"{NORD8}[2]{NC} Compression / Decompression")
        console.print(f"{NORD8}[3]{NC} File Encryption/Decryption (Password)")
        console.print(f"{NORD8}[4]{NC} PGP Operations")
        console.print(f"{NORD8}[5]{NC} Additional Tools")
        console.print(f"{NORD8}[q]{NC} Quit")
        print_divider()
        choice = input(f"{NORD13}Enter your choice: {NC}").strip().lower()
        if choice == "1":
            file_operations_menu()
        elif choice == "2":
            compression_menu()
        elif choice == "3":
            encryption_menu()
        elif choice == "4":
            pgp_menu()
        elif choice == "5":
            additional_menu()
        elif choice == "q":
            logging.info("User exited the tool.")
            console.print(f"{NORD14}Goodbye!{NC}")
            break
        else:
            console.print(
                f"{NORD12}Invalid selection. Please choose a valid option.{NC}"
            )
            time.sleep(1)


# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
def main():
    """
    Main entry point for the script.
    """
    # Ensure log directory exists
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        try:
            os.makedirs(log_dir, exist_ok=True)
        except Exception as e:
            console.print(f"Failed to create log directory: {log_dir}. Error: {e}")
            sys.exit(1)

    try:
        with open(LOG_FILE, "a"):
            pass
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        console.print(
            f"Failed to create or set permissions on log file: {LOG_FILE}. Error: {e}"
        )
        sys.exit(1)

    setup_logging()
    check_root()
    check_dependencies()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"ADVANCED FILE TOOL STARTED AT {now}")
    logging.info("=" * 80)

    # Execute main menu
    main_menu()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"ADVANCED FILE TOOL COMPLETED SUCCESSFULLY AT {now}")
    logging.info("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        if "logging" in sys.modules:
            logging.error(f"Unhandled exception: {ex}")
        else:
            console.print(f"Unhandled exception: {ex}")
        sys.exit(1)
