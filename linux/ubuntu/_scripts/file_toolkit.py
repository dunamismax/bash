#!/usr/bin/env python3
"""
Script Name: file_toolkit.py
--------------------------------------------------------
Description:
  An advanced file encryption, decryption, compression, and file
  management toolkit for Ubuntu. This interactive tool offers a
  Nord-themed menu for performing a wide range of operations:
  file copy, move, delete, advanced search, multicore compression
  (via pigz), password-based encryption/decryption (via OpenSSL), and
  interactive PGP operations (key management, message encryption/decryption,
  signing, and verification).

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

# ------------------------------------------------------------------------------
# Environment Configuration (Modify these settings as needed)
# ------------------------------------------------------------------------------
LOG_FILE = "/var/log/advanced_file_tool.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"
DEFAULT_LOG_LEVEL = "INFO"

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
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
    A custom formatter that applies Nord color theme to log messages.
    """

    def __init__(self, fmt=None, datefmt=None, use_colors=True):
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors and not DISABLE_COLORS

    def format(self, record):
        levelname = record.levelname
        msg = super().format(record)

        if not self.use_colors:
            return msg

        if levelname == "DEBUG":
            return f"{NORD9}{msg}{NC}"
        elif levelname == "INFO":
            return f"{NORD14}{msg}{NC}"
        elif levelname == "WARNING":
            return f"{NORD13}{msg}{NC}"
        elif levelname in ("ERROR", "CRITICAL"):
            return f"{NORD11}{msg}{NC}"
        return msg


def setup_logging():
    """
    Set up logging with console and file handlers, using Nord color theme.
    """
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    # Create logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Clear any existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    # Console handler with colors
    console_formatter = NordColorFormatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler (no colors in file)
    file_formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    try:
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logger.warning(f"Failed to set permissions on log file {LOG_FILE}: {e}")

    return logger


def print_section(title: str):
    """
    Print a section header with Nord theme styling.
    """
    if not DISABLE_COLORS:
        border = "─" * 60
        logging.info(f"{NORD10}{border}{NC}")
        logging.info(f"{NORD10}  {title}{NC}")
        logging.info(f"{NORD10}{border}{NC}")
    else:
        border = "─" * 60
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
    if signum == signal.SIGINT:
        logging.error("Script interrupted by SIGINT (Ctrl+C).")
        sys.exit(130)
    elif signum == signal.SIGTERM:
        logging.error("Script terminated by SIGTERM.")
        sys.exit(143)
    else:
        logging.error(f"Script interrupted by signal {signum}.")
        sys.exit(128 + signum)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def cleanup():
    """
    Perform cleanup tasks before exit.
    """
    logging.info("Performing cleanup tasks before exit.")
    # Additional cleanup tasks can be added here


atexit.register(cleanup)

# ------------------------------------------------------------------------------
# DEPENDENCY CHECKING
# ------------------------------------------------------------------------------


def check_dependencies():
    """
    Check for required dependencies.
    """
    required_commands = ["find", "tar", "pigz", "openssl", "gpg", "md5sum", "sha256sum"]

    missing_commands = []
    for cmd in required_commands:
        if not shutil.which(cmd):
            missing_commands.append(cmd)

    if missing_commands:
        missing_list = ", ".join(missing_commands)
        logging.error(
            f"The following commands are not found in your PATH: {missing_list}"
        )
        print(
            f"{NORD11}The following required commands are missing: {missing_list}{NC}"
        )
        print(f"{NORD11}Please install them and try again.{NC}")
        sys.exit(1)


# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------


def check_root():
    """
    Ensure the script is run with root privileges.
    """
    if os.geteuid() != 0:
        logging.error("This script must be run as root.")
        sys.exit(1)


def print_header():
    """
    Print the application header with Nord styling.
    """
    os.system("clear")
    border = "═" * 60
    print(f"{NORD8}{border}{NC}")
    print(f"{NORD8}  Advanced File & Security Operations Tool {NORD10}v4.0{NC}")
    print(f"{NORD8}{border}{NC}")


def print_divider():
    """
    Print a visual divider with Nord styling.
    """
    print(f"{NORD8}{'─' * 60}{NC}")


def prompt_enter():
    """
    Wait for user to press Enter to continue.
    """
    input(f"{NORD13}Press Enter to continue...{NC}")


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
        print(f"{NORD11}Error: Source '{src}' does not exist.{NC}")
        return

    try:
        if os.path.isdir(src):
            # Copy directory recursively
            shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dest)
        logging.info(f"Copied '{src}' to '{dest}' successfully.")
        print(f"{NORD14}Copy completed successfully.{NC}")
    except Exception as e:
        logging.error(f"Copy failed: {e}")
        print(f"{NORD11}Error: Copy failed - {e}{NC}")


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
        print(f"{NORD11}Error: Source '{src}' does not exist.{NC}")
        return

    try:
        shutil.move(src, dest)
        logging.info(f"Moved '{src}' to '{dest}' successfully.")
        print(f"{NORD14}Move completed successfully.{NC}")
    except Exception as e:
        logging.error(f"Move failed: {e}")
        print(f"{NORD11}Error: Move failed - {e}{NC}")


def file_delete():
    """
    Delete a file or directory.
    """
    print_section("File Deletion Operation")
    logging.info("Initiating file deletion operation.")

    target = input(f"{NORD13}Enter file/directory to delete: {NC}").strip()

    if not os.path.exists(target):
        logging.error(f"Target '{target}' does not exist.")
        print(f"{NORD11}Error: Target '{target}' does not exist.{NC}")
        return

    confirm = (
        input(f"{NORD13}Are you sure you want to delete '{target}'? (y/n): {NC}")
        .strip()
        .lower()
    )

    if confirm.startswith("y"):
        try:
            if os.path.isdir(target):
                shutil.rmtree(target)
            else:
                os.remove(target)
            logging.info(f"Deleted '{target}' successfully.")
            print(f"{NORD14}Deletion completed successfully.{NC}")
        except Exception as e:
            logging.error(f"Deletion failed: {e}")
            print(f"{NORD11}Error: Deletion failed - {e}{NC}")
    else:
        logging.warning("Deletion cancelled by user.")
        print(f"{NORD12}Deletion cancelled.{NC}")


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
        print(f"{NORD11}Error: Directory '{search_dir}' does not exist.{NC}")
        return

    print(f"{NORD14}Search results:{NC}")
    try:
        result = subprocess.run(
            ["find", search_dir, "-type", "f", "-name", pattern],
            check=True,
            text=True,
            capture_output=True,
        )
        if result.stdout.strip():
            print(result.stdout)
        else:
            print(f"{NORD13}No files found matching the pattern.{NC}")
        logging.info(f"Search completed in '{search_dir}' for pattern '{pattern}'.")
    except subprocess.CalledProcessError as e:
        logging.error(f"File search failed: {e}")
        print(f"{NORD11}Error: File search failed - {e.stderr}{NC}")


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
        print(f"{NORD11}Error: Target '{target}' does not exist.{NC}")
        return

    outfile = input(
        f"{NORD13}Enter output archive name (e.g., archive.tar.gz): {NC}"
    ).strip()

    # Build and execute: tar -cf - target | pigz > outfile
    cmd = f"tar -cf - {target} | pigz > {outfile}"
    try:
        print(f"{NORD13}Compressing... Please wait.{NC}")
        subprocess.run(cmd, shell=True, check=True)
        logging.info(f"Compressed '{target}' to '{outfile}' successfully.")
        print(f"{NORD14}Compression completed successfully.{NC}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Compression failed: {e}")
        print(f"{NORD11}Error: Compression failed - {e}{NC}")


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
        print(f"{NORD11}Error: File '{infile}' does not exist.{NC}")
        return

    outdir = input(f"{NORD13}Enter output directory: {NC}").strip()

    try:
        os.makedirs(outdir, exist_ok=True)
    except Exception as e:
        logging.error(f"Failed to create output directory: {e}")
        print(f"{NORD11}Error: Failed to create output directory - {e}{NC}")
        return

    # Execute: pigz -dc infile | tar -xf - -C outdir
    cmd = f"pigz -dc {infile} | tar -xf - -C {outdir}"
    try:
        print(f"{NORD13}Decompressing... Please wait.{NC}")
        subprocess.run(cmd, shell=True, check=True)
        logging.info(f"Decompressed '{infile}' to '{outdir}' successfully.")
        print(f"{NORD14}Decompression completed successfully.{NC}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Decompression failed: {e}")
        print(f"{NORD11}Error: Decompression failed - {e}{NC}")


# ------------------------------------------------------------------------------
# FILE ENCRYPTION / DECRYPTION (PASSWORD-BASED using OpenSSL)
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
        print(f"{NORD11}Error: File '{infile}' does not exist.{NC}")
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
        print(f"{NORD13}Encrypting... Please wait.{NC}")
        subprocess.run(cmd, check=True, capture_output=True)
        logging.info(f"Encrypted '{infile}' to '{outfile}' successfully.")
        print(f"{NORD14}File encrypted successfully.{NC}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Encryption failed: {e}")
        print(f"{NORD11}Error: Encryption failed - {e.stderr.decode()}{NC}")


def decrypt_file():
    """
    Decrypt a file using OpenSSL (AES-256-CBC).
    """
    print_section("File Decryption")
    logging.info("Initiating file decryption.")

    infile = input(f"{NORD13}Enter file to decrypt: {NC}").strip()

    if not os.path.isfile(infile):
        logging.error(f"File '{infile}' does not exist.")
        print(f"{NORD11}Error: File '{infile}' does not exist.{NC}")
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
        print(f"{NORD13}Decrypting... Please wait.{NC}")
        subprocess.run(cmd, check=True, capture_output=True)
        logging.info(f"Decrypted '{infile}' to '{outfile}' successfully.")
        print(f"{NORD14}File decrypted successfully.{NC}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Decryption failed: {e}")
        print(f"{NORD11}Error: Decryption failed - {e.stderr.decode()}{NC}")
        print(f"{NORD12}Hint: Check if the password is correct.{NC}")


# ------------------------------------------------------------------------------
# PGP OPERATIONS FUNCTIONS (using gpg)
# ------------------------------------------------------------------------------


def pgp_create_key():
    """
    Create a new PGP key pair using GPG.
    """
    print_section("PGP Key Generation")
    logging.info("Starting interactive PGP key generation.")

    print(f"{NORD13}This will launch the interactive GPG key generation wizard.{NC}")
    print(f"{NORD13}Follow the prompts to create your key.{NC}")
    time.sleep(1)

    try:
        subprocess.run(["gpg", "--gen-key"], check=True)
        logging.info("PGP key generation completed.")
        print(f"{NORD14}PGP key generation completed successfully.{NC}")
    except subprocess.CalledProcessError as e:
        logging.error(f"PGP key generation failed: {e}")
        print(f"{NORD11}Error: PGP key generation failed - {e}{NC}")


def pgp_encrypt_message():
    """
    Encrypt a message using PGP.
    """
    print_section("PGP Message Encryption")
    logging.info("Initiating PGP message encryption.")

    recipient = input(f"{NORD13}Enter recipient's email or key ID: {NC}").strip()
    print(
        f"{NORD14}Enter the message to encrypt. End input with a single '.' on a new line.{NC}"
    )

    lines = []
    while True:
        line = input()
        if line.strip() == ".":
            break
        lines.append(line)

    msg = "\n".join(lines)

    try:
        proc = subprocess.run(
            ["gpg", "--encrypt", "--armor", "-r", recipient],
            input=msg,
            text=True,
            check=True,
            capture_output=True,
        )
        print(f"{NORD14}Encrypted message:{NC}")
        print(proc.stdout)
        logging.info("Message encrypted successfully.")
    except subprocess.CalledProcessError as e:
        logging.error(f"PGP encryption failed: {e}")
        print(f"{NORD11}Error: PGP encryption failed - {e.stderr}{NC}")


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
        print(f"{NORD11}Error: File '{infile}' does not exist.{NC}")
        return

    try:
        print(f"{NORD14}Decrypted message:{NC}")
        subprocess.run(["gpg", "--decrypt", infile], check=True)
        logging.info("PGP decryption completed.")
    except subprocess.CalledProcessError as e:
        logging.error(f"PGP decryption failed: {e}")
        print(f"{NORD11}Error: PGP decryption failed - {e}{NC}")


def pgp_sign_message():
    """
    Sign a message with your PGP key.
    """
    print_section("PGP Message Signing")
    logging.info("Initiating message signing with PGP.")

    print(
        f"{NORD14}Enter the message to sign. End input with a single '.' on a new line.{NC}"
    )

    lines = []
    while True:
        line = input()
        if line.strip() == ".":
            break
        lines.append(line)

    msg = "\n".join(lines)

    try:
        result = subprocess.run(
            ["gpg", "--clearsign"],
            input=msg,
            text=True,
            check=True,
            capture_output=True,
        )
        print(f"{NORD14}Signed message:{NC}")
        print(result.stdout)
        logging.info("Message signed successfully.")
    except subprocess.CalledProcessError as e:
        logging.error(f"PGP signing failed: {e}")
        print(f"{NORD11}Error: PGP signing failed - {e.stderr}{NC}")


def pgp_verify_signature():
    """
    Verify a PGP signature.
    """
    print_section("PGP Signature Verification")
    logging.info("Initiating PGP signature verification.")

    infile = input(f"{NORD13}Enter the signed file to verify: {NC}").strip()

    if not os.path.isfile(infile):
        logging.error(f"File '{infile}' does not exist.")
        print(f"{NORD11}Error: File '{infile}' does not exist.{NC}")
        return

    try:
        result = subprocess.run(
            ["gpg", "--verify", infile], check=True, capture_output=True, text=True
        )
        print(f"{NORD14}Verification result:{NC}")
        if result.stderr:  # GPG prints verification info to stderr
            print(result.stderr)
        logging.info("Signature verified successfully.")
        print(f"{NORD14}Signature verification completed.{NC}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Signature verification failed: {e}")
        print(f"{NORD11}Error: Signature verification failed.{NC}")
        if e.stderr:
            print(e.stderr)


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
        print(f"{NORD11}Error: File '{file_path}' does not exist.{NC}")
        return

    print(f"{NORD14}Select checksum type:{NC}")
    print(f"{NORD8}[1]{NC} MD5")
    print(f"{NORD8}[2]{NC} SHA256")

    choice = input(f"{NORD13}Enter choice (1 or 2): {NC}").strip()

    if choice == "1":
        cmd = ["md5sum", file_path]
        checksum_type = "MD5"
    elif choice == "2":
        cmd = ["sha256sum", file_path]
        checksum_type = "SHA256"
    else:
        logging.warning("Invalid checksum type selection.")
        print(f"{NORD12}Invalid selection.{NC}")
        return

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"{NORD14}{checksum_type} Checksum:{NC}")
        print(result.stdout)
        logging.info(f"Calculated {checksum_type} checksum for '{file_path}'.")
    except subprocess.CalledProcessError as e:
        logging.error(f"Checksum calculation failed: {e}")
        print(f"{NORD11}Error: Checksum calculation failed - {e}{NC}")


# ------------------------------------------------------------------------------
# INTERACTIVE MENUS
# ------------------------------------------------------------------------------


def file_operations_menu():
    """
    Display and handle the file operations menu.
    """
    while True:
        print_header()
        print(f"{NORD14}File Operations:{NC}")
        print_divider()
        print(f"{NORD8}[1]{NC} Copy File/Directory")
        print(f"{NORD8}[2]{NC} Move File/Directory")
        print(f"{NORD8}[3]{NC} Delete File/Directory")
        print(f"{NORD8}[4]{NC} Advanced Search")
        print(f"{NORD8}[0]{NC} Return to Main Menu")
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
            print(f"{NORD12}Invalid selection.{NC}")
            time.sleep(1)


def compression_menu():
    """
    Display and handle the compression menu.
    """
    while True:
        print_header()
        print(f"{NORD14}Compression / Decompression (using pigz):{NC}")
        print_divider()
        print(f"{NORD8}[1]{NC} Compress File/Directory")
        print(f"{NORD8}[2]{NC} Decompress File")
        print(f"{NORD8}[0]{NC} Return to Main Menu")
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
            print(f"{NORD12}Invalid selection.{NC}")
            time.sleep(1)


def encryption_menu():
    """
    Display and handle the encryption menu.
    """
    while True:
        print_header()
        print(f"{NORD14}File Encryption / Decryption (Password-based):{NC}")
        print_divider()
        print(f"{NORD8}[1]{NC} Encrypt a File")
        print(f"{NORD8}[2]{NC} Decrypt a File")
        print(f"{NORD8}[0]{NC} Return to Main Menu")
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
            print(f"{NORD12}Invalid selection.{NC}")
            time.sleep(1)


def pgp_menu():
    """
    Display and handle the PGP operations menu.
    """
    while True:
        print_header()
        print(f"{NORD14}PGP Operations:{NC}")
        print_divider()
        print(f"{NORD8}[1]{NC} Create PGP Key")
        print(f"{NORD8}[2]{NC} Encrypt Message")
        print(f"{NORD8}[3]{NC} Decrypt Message")
        print(f"{NORD8}[4]{NC} Sign Message")
        print(f"{NORD8}[5]{NC} Verify Signature")
        print(f"{NORD8}[0]{NC} Return to Main Menu")
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
            print(f"{NORD12}Invalid selection.{NC}")
            time.sleep(1)


def additional_menu():
    """
    Display and handle the additional tools menu.
    """
    while True:
        print_header()
        print(f"{NORD14}Additional Tools:{NC}")
        print_divider()
        print(f"{NORD8}[1]{NC} Calculate File Checksum")
        print(f"{NORD8}[0]{NC} Return to Main Menu")
        print_divider()

        choice = input(f"{NORD13}Enter your choice: {NC}").strip()

        if choice == "1":
            calculate_checksum()
            prompt_enter()
        elif choice == "0":
            break
        else:
            print(f"{NORD12}Invalid selection.{NC}")
            time.sleep(1)


def main_menu():
    """
    Display and handle the main menu.
    """
    while True:
        print_header()
        print(f"{NORD14}Main Menu:{NC}")
        print_divider()
        print(f"{NORD8}[1]{NC} File Operations")
        print(f"{NORD8}[2]{NC} Compression / Decompression")
        print(f"{NORD8}[3]{NC} File Encryption/Decryption (Password)")
        print(f"{NORD8}[4]{NC} PGP Operations")
        print(f"{NORD8}[5]{NC} Additional Tools")
        print(f"{NORD8}[q]{NC} Quit")
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
            print(f"{NORD14}Goodbye!{NC}")
            return
        else:
            print(f"{NORD12}Invalid selection. Please choose a valid option.{NC}")
            time.sleep(1)


# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------


def main():
    """
    Main entry point for the script.
    """
    # Ensure the log directory exists before we attempt to log anything
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        try:
            os.makedirs(log_dir, exist_ok=True)
        except Exception as e:
            print(f"Failed to create log directory: {log_dir}. Error: {e}")
            sys.exit(1)

    try:
        with open(LOG_FILE, "a"):
            pass
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        print(
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

    # Finish up
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info("=" * 80)
    logging.info(f"ADVANCED FILE TOOL COMPLETED SUCCESSFULLY AT {now}")
    logging.info("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        # This catches any unhandled exceptions
        if "logging" in sys.modules:
            logging.error(f"Unhandled exception: {ex}")
        else:
            print(f"Unhandled exception: {ex}")
        sys.exit(1)
