#!/usr/bin/env python3
"""
Script Name: advanced_file_tool.py
Description: An advanced file encryption, decryption, compression, and file
             management toolkit for Ubuntu. This interactive tool offers a
             Nord‑themed menu for performing a wide range of operations:
             file copy, move, delete, advanced search, multicore compression
             (via pigz), password‑based encryption/decryption (via OpenSSL), and
             interactive PGP operations (key management, message encryption/decryption,
             signing, and verification).
Author: Your Name | License: MIT | Version: 3.1
Usage:
  sudo ./advanced_file_tool.py
Notes:
  - Some operations require root privileges.
  - Logs are stored in /var/log/advanced_file_tool.log by default.
"""

import os
import sys
import subprocess
import logging
import signal
import atexit
import time
import getpass
import shutil

# ------------------------------------------------------------------------------
# GLOBAL VARIABLES & CONFIGURATION
# ------------------------------------------------------------------------------
LOG_FILE = "/var/log/advanced_file_tool.log"
DISABLE_COLORS = os.environ.get("DISABLE_COLORS", "false").lower() == "true"

# ------------------------------------------------------------------------------
# NORD COLOR THEME CONSTANTS (24-bit ANSI escape sequences)
# ------------------------------------------------------------------------------
NORD0 = '\033[38;2;46;52;64m'      # Dark background (#2E3440)
NORD1 = '\033[38;2;59;66;82m'
NORD2 = '\033[38;2;67;76;94m'
NORD3 = '\033[38;2;76;86;106m'
NORD4 = '\033[38;2;216;222;233m'   # Light gray text (#D8DEE9)
NORD5 = '\033[38;2;229;233;240m'
NORD6 = '\033[38;2;236;239;244m'
NORD7 = '\033[38;2;143;188;187m'   # Teal for success/info (#8FBCBB)
NORD8 = '\033[38;2;136;192;208m'   # Accent blue for headings (#88C0D0)
NORD9 = '\033[38;2;129;161;193m'   # Blue for debug (#81A1C1)
NORD10 = '\033[38;2;94;129;172m'   # Purple for highlights (#5E81AC)
NORD11 = '\033[38;2;191;97;106m'   # Red for errors (#BF616A)
NORD12 = '\033[38;2;208;135;112m'  # Orange for warnings (#D08770)
NORD13 = '\033[38;2;235;203;139m'  # Yellow for labels (#EBCB8B)
NORD14 = '\033[38;2;163;190;140m'  # Green for OK messages (#A3BE8C)
NC = '\033[0m'                    # Reset / No Color

# ------------------------------------------------------------------------------
# LOGGING SETUP
# ------------------------------------------------------------------------------
class ColorFormatter(logging.Formatter):
    LEVEL_COLORS = {
        "DEBUG": NORD9,
        "INFO": NORD14,
        "WARNING": NORD12,
        "ERROR": NORD11,
        "CRITICAL": NORD11,
    }
    def format(self, record):
        message = super().format(record)
        if not DISABLE_COLORS:
            color = self.LEVEL_COLORS.get(record.levelname, NC)
            message = f"{color}{message}{NC}"
        return message

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s",
                                  "%Y-%m-%d %H:%M:%S")
    # File handler
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    # Console handler (with colors)
    console_handler = logging.StreamHandler(sys.stderr)
    console_formatter = ColorFormatter("[%(asctime)s] [%(levelname)s] %(message)s",
                                       "%Y-%m-%d %H:%M:%S")
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    try:
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        logging.warning(f"Failed to set permissions on {LOG_FILE}: {e}")

# ------------------------------------------------------------------------------
# ERROR HANDLING & CLEANUP FUNCTIONS
# ------------------------------------------------------------------------------
def handle_error(error_message="An unknown error occurred.", exit_code=1):
    logging.error(f"{error_message} (Exit Code: {exit_code})")
    sys.exit(exit_code)

def cleanup():
    logging.info("Performing cleanup tasks before exit.")
    # Place any necessary cleanup tasks here (e.g., temporary file removal)

atexit.register(cleanup)

def signal_handler(signum, frame):
    handle_error(f"Script interrupted by signal {signum}.", exit_code=128+signum)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ------------------------------------------------------------------------------
# HELPER & UTILITY FUNCTIONS
# ------------------------------------------------------------------------------
def check_root():
    if os.geteuid() != 0:
        handle_error("This script must be run as root.")

def print_header():
    os.system("clear")
    border = "─" * 60
    print(f"{NORD8}{border}{NC}")
    print(f"{NORD8}  Advanced File & Security Operations Tool  {NC}")
    print(f"{NORD8}{border}{NC}")

def print_divider():
    print(f"{NORD8}{'-'*60}{NC}")

def prompt_enter():
    input("Press Enter to continue...")

# ------------------------------------------------------------------------------
# FILE OPERATIONS FUNCTIONS
# ------------------------------------------------------------------------------
def file_copy():
    logging.info("Initiating file copy operation.")
    src = input("Enter source file/directory: ").strip()
    dest = input("Enter destination path: ").strip()
    if not os.path.exists(src):
        handle_error(f"Source '{src}' does not exist.")
    try:
        if os.path.isdir(src):
            # Copy directory recursively
            shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dest)
        logging.info("Copy completed successfully.")
    except Exception as e:
        handle_error(f"Copy failed: {e}")

def file_move():
    logging.info("Initiating file move operation.")
    src = input("Enter source file/directory: ").strip()
    dest = input("Enter destination path: ").strip()
    if not os.path.exists(src):
        handle_error(f"Source '{src}' does not exist.")
    try:
        shutil.move(src, dest)
        logging.info("Move completed successfully.")
    except Exception as e:
        handle_error(f"Move failed: {e}")

def file_delete():
    logging.info("Initiating file deletion operation.")
    target = input("Enter file/directory to delete: ").strip()
    if not os.path.exists(target):
        handle_error(f"Target '{target}' does not exist.")
    confirm = input(f"Are you sure you want to delete '{target}'? (y/n): ").strip().lower()
    if confirm.startswith('y'):
        try:
            if os.path.isdir(target):
                shutil.rmtree(target)
            else:
                os.remove(target)
            logging.info("Deletion completed successfully.")
        except Exception as e:
            handle_error(f"Deletion failed: {e}")
    else:
        logging.warning("Deletion cancelled by user.")
        print(f"{NORD12}Deletion cancelled.{NC}")

def file_search():
    logging.info("Initiating advanced file search.")
    search_dir = input("Enter directory to search in: ").strip()
    pattern = input("Enter filename pattern (e.g., *.txt): ").strip()
    if not os.path.isdir(search_dir):
        handle_error(f"Directory '{search_dir}' does not exist.")
    print(f"{NORD14}Search results:{NC}")
    try:
        result = subprocess.run(["find", search_dir, "-type", "f", "-name", pattern],
                                check=True, text=True, capture_output=True)
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        handle_error(f"File search failed: {e}")
    prompt_enter()

# ------------------------------------------------------------------------------
# COMPRESSION / DECOMPRESSION FUNCTIONS (using pigz)
# ------------------------------------------------------------------------------
def compress_file():
    logging.info("Initiating compression operation.")
    target = input("Enter file or directory to compress: ").strip()
    if not os.path.exists(target):
        handle_error(f"Target '{target}' does not exist.")
    outfile = input("Enter output archive name (e.g., archive.tar.gz): ").strip()
    # Build and execute: tar -cf - target | pigz > outfile
    cmd = f"tar -cf - {target} | pigz > {outfile}"
    try:
        subprocess.run(cmd, shell=True, check=True)
        logging.info("Compression completed successfully.")
    except subprocess.CalledProcessError as e:
        handle_error(f"Compression failed: {e}")

def decompress_file():
    logging.info("Initiating decompression operation.")
    infile = input("Enter compressed file (e.g., archive.tar.gz): ").strip()
    if not os.path.isfile(infile):
        handle_error(f"File '{infile}' does not exist.")
    outdir = input("Enter output directory: ").strip()
    try:
        os.makedirs(outdir, exist_ok=True)
    except Exception as e:
        handle_error(f"Failed to create output directory: {e}")
    # Execute: pigz -dc infile | tar -xf - -C outdir
    cmd = f"pigz -dc {infile} | tar -xf - -C {outdir}"
    try:
        subprocess.run(cmd, shell=True, check=True)
        logging.info("Decompression completed successfully.")
    except subprocess.CalledProcessError as e:
        handle_error(f"Decompression failed: {e}")

# ------------------------------------------------------------------------------
# FILE ENCRYPTION / DECRYPTION (PASSWORD-BASED using OpenSSL)
# ------------------------------------------------------------------------------
def encrypt_file():
    logging.info("Initiating file encryption.")
    infile = input("Enter file to encrypt: ").strip()
    if not os.path.isfile(infile):
        handle_error(f"File '{infile}' does not exist.")
    outfile = input("Enter output encrypted file name: ").strip()
    password = getpass.getpass("Enter password: ")
    cmd = ["openssl", "enc", "-aes-256-cbc", "-salt",
           "-in", infile, "-out", outfile, "-pass", f"pass:{password}"]
    try:
        subprocess.run(cmd, check=True)
        logging.info("File encrypted successfully.")
    except subprocess.CalledProcessError as e:
        handle_error(f"Encryption failed: {e}")

def decrypt_file():
    logging.info("Initiating file decryption.")
    infile = input("Enter file to decrypt: ").strip()
    if not os.path.isfile(infile):
        handle_error(f"File '{infile}' does not exist.")
    outfile = input("Enter output decrypted file name: ").strip()
    password = getpass.getpass("Enter password: ")
    cmd = ["openssl", "enc", "-d", "-aes-256-cbc",
           "-in", infile, "-out", outfile, "-pass", f"pass:{password}"]
    try:
        subprocess.run(cmd, check=True)
        logging.info("File decrypted successfully.")
    except subprocess.CalledProcessError as e:
        handle_error(f"Decryption failed: {e}")

# ------------------------------------------------------------------------------
# PGP OPERATIONS FUNCTIONS (using gpg)
# ------------------------------------------------------------------------------
def pgp_create_key():
    logging.info("Starting interactive PGP key generation.")
    try:
        subprocess.run(["gpg", "--gen-key"], check=True)
        logging.info("PGP key generation completed.")
    except subprocess.CalledProcessError as e:
        handle_error(f"PGP key generation failed: {e}")

def pgp_encrypt_message():
    logging.info("Initiating PGP message encryption.")
    recipient = input("Enter recipient's email or key ID: ").strip()
    print(f"{NORD14}Enter the message to encrypt. End input with a single '.' on a new line.{NC}")
    lines = []
    while True:
        line = input()
        if line.strip() == ".":
            break
        lines.append(line)
    msg = "\n".join(lines)
    try:
        proc = subprocess.run(["gpg", "--encrypt", "--armor", "-r", recipient],
                              input=msg, text=True, check=True)
        logging.info("Message encrypted successfully.")
    except subprocess.CalledProcessError as e:
        handle_error(f"PGP encryption failed: {e}")

def pgp_decrypt_message():
    logging.info("Initiating PGP message decryption.")
    infile = input("Enter file containing the PGP encrypted message: ").strip()
    if not os.path.isfile(infile):
        handle_error(f"File '{infile}' does not exist.")
    try:
        subprocess.run(["gpg", "--decrypt", infile], check=True)
        logging.info("PGP decryption completed.")
    except subprocess.CalledProcessError as e:
        handle_error(f"PGP decryption failed: {e}")

def pgp_sign_message():
    logging.info("Initiating message signing with PGP.")
    print(f"{NORD14}Enter the message to sign. End input with a single '.' on a new line.{NC}")
    lines = []
    while True:
        line = input()
        if line.strip() == ".":
            break
        lines.append(line)
    msg = "\n".join(lines)
    try:
        subprocess.run(["gpg", "--clearsign"], input=msg, text=True, check=True)
        logging.info("Message signed successfully.")
    except subprocess.CalledProcessError as e:
        handle_error(f"PGP signing failed: {e}")

def pgp_verify_signature():
    logging.info("Initiating PGP signature verification.")
    infile = input("Enter the signed file to verify: ").strip()
    if not os.path.isfile(infile):
        handle_error(f"File '{infile}' does not exist.")
    try:
        subprocess.run(["gpg", "--verify", infile], check=True)
        logging.info("Signature verified successfully.")
    except subprocess.CalledProcessError as e:
        handle_error(f"Signature verification failed: {e}")

# ------------------------------------------------------------------------------
# ADDITIONAL TOOLS FUNCTIONS
# ------------------------------------------------------------------------------
def calculate_checksum():
    logging.info("Starting checksum calculation.")
    file_path = input("Enter file to calculate checksum: ").strip()
    if not os.path.isfile(file_path):
        handle_error(f"File '{file_path}' does not exist.")
    print(f"{NORD14}Select checksum type:{NC}")
    print(f"{NORD8}[1]{NC} MD5")
    print(f"{NORD8}[2]{NC} SHA256")
    choice = input("Enter choice (1 or 2): ").strip()
    if choice == "1":
        cmd = ["md5sum", file_path]
    elif choice == "2":
        cmd = ["sha256sum", file_path]
    else:
        logging.warning("Invalid checksum type selection.")
        print(f"{NORD12}Invalid selection.{NC}")
        return
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        handle_error(f"Checksum calculation failed: {e}")
    prompt_enter()

# ------------------------------------------------------------------------------
# INTERACTIVE MENUS
# ------------------------------------------------------------------------------
def file_operations_menu():
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
        choice = input("Enter your choice: ").strip()
        if choice == "1":
            file_copy(); prompt_enter()
        elif choice == "2":
            file_move(); prompt_enter()
        elif choice == "3":
            file_delete(); prompt_enter()
        elif choice == "4":
            file_search()
        elif choice == "0":
            break
        else:
            print(f"{NORD12}Invalid selection.{NC}")
            time.sleep(1)

def compression_menu():
    while True:
        print_header()
        print(f"{NORD14}Compression / Decompression (using pigz):{NC}")
        print_divider()
        print(f"{NORD8}[1]{NC} Compress File/Directory")
        print(f"{NORD8}[2]{NC} Decompress File")
        print(f"{NORD8}[0]{NC} Return to Main Menu")
        print_divider()
        choice = input("Enter your choice: ").strip()
        if choice == "1":
            compress_file(); prompt_enter()
        elif choice == "2":
            decompress_file(); prompt_enter()
        elif choice == "0":
            break
        else:
            print(f"{NORD12}Invalid selection.{NC}")
            time.sleep(1)

def encryption_menu():
    while True:
        print_header()
        print(f"{NORD14}File Encryption / Decryption (Password-based):{NC}")
        print_divider()
        print(f"{NORD8}[1]{NC} Encrypt a File")
        print(f"{NORD8}[2]{NC} Decrypt a File")
        print(f"{NORD8}[0]{NC} Return to Main Menu")
        print_divider()
        choice = input("Enter your choice: ").strip()
        if choice == "1":
            encrypt_file(); prompt_enter()
        elif choice == "2":
            decrypt_file(); prompt_enter()
        elif choice == "0":
            break
        else:
            print(f"{NORD12}Invalid selection.{NC}")
            time.sleep(1)

def pgp_menu():
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
        choice = input("Enter your choice: ").strip()
        if choice == "1":
            pgp_create_key(); prompt_enter()
        elif choice == "2":
            pgp_encrypt_message(); prompt_enter()
        elif choice == "3":
            pgp_decrypt_message(); prompt_enter()
        elif choice == "4":
            pgp_sign_message(); prompt_enter()
        elif choice == "5":
            pgp_verify_signature(); prompt_enter()
        elif choice == "0":
            break
        else:
            print(f"{NORD12}Invalid selection.{NC}")
            time.sleep(1)

def additional_menu():
    while True:
        print_header()
        print(f"{NORD14}Additional Tools:{NC}")
        print_divider()
        print(f"{NORD8}[1]{NC} Calculate File Checksum")
        print(f"{NORD8}[0]{NC} Return to Main Menu")
        print_divider()
        choice = input("Enter your choice: ").strip()
        if choice == "1":
            calculate_checksum()
        elif choice == "0":
            break
        else:
            print(f"{NORD12}Invalid selection.{NC}")
            time.sleep(1)

def main_menu():
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
        choice = input("Enter your choice: ").strip().lower()
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
            logging.info("User exited the tool. Goodbye!")
            print(f"{NORD14}Goodbye!{NC}")
            sys.exit(0)
        else:
            print(f"{NORD12}Invalid selection. Please choose a valid option.{NC}")
            time.sleep(1)

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------
def main():
    check_root()
    # Ensure the log directory exists and secure the log file.
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.isdir(log_dir):
        try:
            os.makedirs(log_dir, exist_ok=True)
        except Exception as e:
            handle_error(f"Failed to create log directory: {log_dir}. Error: {e}")
    try:
        with open(LOG_FILE, "a"):
            pass
        os.chmod(LOG_FILE, 0o600)
    except Exception as e:
        handle_error(f"Failed to create or set permissions on log file: {LOG_FILE}. Error: {e}")
    setup_logging()
    logging.info("Script execution started.")
    main_menu()

if __name__ == "__main__":
    main()