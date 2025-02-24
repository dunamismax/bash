#!/usr/bin/env python3
"""
Standalone script to install/update Visual Studio Code Stable and modify
its desktop shortcut for Wayland support.
"""

import os
import subprocess
import sys
import shutil
import logging

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

def print_section(title: str) -> None:
    border = "=" * 60
    logging.info("\n%s\n%s\n%s\n", border, title, border)

def run_command(cmd, check=True, capture_output=False, text=True):
    logging.info("Running command: %s", " ".join(cmd) if isinstance(cmd, list) else cmd)
    return subprocess.run(cmd, check=check, capture_output=capture_output, text=text)

def log_info(message: str) -> None:
    logging.info(message)

def log_warn(message: str) -> None:
    logging.warning(message)

def handle_error(message: str, code: int = 1) -> None:
    logging.error(message)
    sys.exit(code)

def install_configure_vscode_stable() -> None:
    """
    Install Visual Studio Code - Stable and configure it to run natively on Wayland.

    This function performs the following steps:
      1. Downloads the VS Code stable .deb package from the provided URL.
      2. Installs the package (fixing dependencies if necessary).
      3. Overwrites the system-wide desktop file (/usr/share/applications/code.desktop)
         with custom content.
      4. Copies the .desktop file to the user's local applications directory so updates won’t overwrite it.
      5. Modifies the local copy to ensure the Exec line includes Wayland flags and sets StartupWMClass appropriately.
    """
    print_section("Visual Studio Code - Stable Installation and Configuration")
    vscode_url = (
        "https://vscode.download.prss.microsoft.com/dbazure/download/stable/e54c774e0add60467559eb0d1e229c6452cf8447/code_1.97.2-1739406807_amd64.deb"
    )
    deb_path = "/tmp/code.deb"

    # Step 1: Download VS Code Stable
    try:
        log_info("Downloading VS Code Stable...")
        run_command(["curl", "-L", "-o", deb_path, vscode_url])
    except subprocess.CalledProcessError as e:
        handle_error(f"Failed to download VS Code Stable: {e}")
        return

    # Step 2: Install VS Code Stable
    try:
        log_info("Installing VS Code Stable...")
        run_command(["dpkg", "-i", deb_path])
    except subprocess.CalledProcessError:
        log_warn("dpkg installation encountered issues. Attempting to fix dependencies...")
        try:
            run_command(["apt", "install", "-f", "-y"])
        except subprocess.CalledProcessError as e:
            handle_error(f"Failed to fix dependencies for VS Code Stable: {e}")

    # Clean up the downloaded .deb file
    try:
        os.remove(deb_path)
    except Exception:
        pass

    # Step 3: Overwrite system-wide .desktop file
    desktop_file_path = "/usr/share/applications/code.desktop"
    desktop_content = """[Desktop Entry]
Name=Visual Studio Code
Comment=Code Editing. Redefined.
GenericName=Text Editor
Exec=/usr/share/code/code --enable-features=UseOzonePlatform --ozone-platform=wayland %F
Icon=vscode
Type=Application
StartupNotify=false
StartupWMClass=Code
Categories=TextEditor;Development;IDE;
MimeType=application/x-code-workspace;
Actions=new-empty-window;
Keywords=vscode;

[Desktop Action new-empty-window]
Name=New Empty Window
Name[de]=Neues leeres Fenster
Name[es]=Nueva ventana vacía
Name[fr]=Nouvelle fenêtre vide
Name[it]=Nuova finestra vuota
Name[ja]=新しい空のウィンドウ
Name[ko]=새 빈 창
Name[ru]=Новое пустое окно
Name[zh_CN]=新建空窗口
Name[zh_TW]=開新空視窗
Exec=/usr/share/code/code --new-window --enable-features=UseOzonePlatform --ozone-platform=wayland %F
Icon=vscode
"""
    try:
        with open(desktop_file_path, "w") as f:
            f.write(desktop_content)
        log_info(f"Updated system-wide desktop file: {desktop_file_path}")
    except Exception as e:
        log_warn(f"Failed to update system-wide desktop file: {e}")

    # Step 4: Copy desktop file to local applications directory
    local_app_dir = os.path.expanduser("~/.local/share/applications")
    local_desktop_file = os.path.join(local_app_dir, "code.desktop")
    try:
        os.makedirs(local_app_dir, exist_ok=True)
        shutil.copy2(desktop_file_path, local_desktop_file)
        log_info(f"Copied desktop file to local directory: {local_desktop_file}")
    except Exception as e:
        log_warn(f"Failed to copy desktop file to local applications directory: {e}")

    # Step 5: Modify the local desktop file for Wayland and proper icon handling
    try:
        with open(local_desktop_file, "r") as f:
            lines = f.readlines()
        new_lines = []
        for line in lines:
            if line.startswith("Exec="):
                if "new-window" in line:
                    new_lines.append("Exec=/usr/share/code/code --new-window --enable-features=UseOzonePlatform --ozone-platform=wayland %F\n")
                else:
                    new_lines.append("Exec=/usr/share/code/code --enable-features=UseOzonePlatform --ozone-platform=wayland %F\n")
            elif line.startswith("StartupWMClass="):
                new_lines.append("StartupWMClass=code\n")
            else:
                new_lines.append(line)
        with open(local_desktop_file, "w") as f:
            f.writelines(new_lines)
        log_info(f"Local desktop file updated for Wayland compatibility: {local_desktop_file}")
    except Exception as e:
        log_warn(f"Failed to modify local desktop file: {e}")

def main() -> None:
    install_configure_vscode_stable()

if __name__ == "__main__":
    main()
