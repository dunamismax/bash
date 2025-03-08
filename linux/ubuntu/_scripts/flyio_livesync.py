#!/usr/bin/env python3
"""
Initial version 7th Feb. 2024

This script installs and configures Obsidian Livesync on Fly.io.
It installs prerequisites (Fly.io CLI, Deno, jq), clones the repository,
prompts for Fly.io authentication and region selection, deploys the server,
and finally displays the resulting setup URI.
"""

import os
import sys
import time
import json
import shutil
import signal
import asyncio
import subprocess
import atexit
from typing import Tuple

import pyfiglet
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text
from rich.traceback import install as install_rich_traceback

# Setup Rich traceback for better error messages
install_rich_traceback(show_locals=True)
console: Console = Console()

# Application Constants
APP_NAME: str = "Obsidian Livesync Installer"
VERSION: str = "7th Feb. 2024"

# UI Helper Functions
def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def create_header() -> Panel:
    term_width, _ = shutil.get_terminal_size((80, 24))
    try:
        fig = pyfiglet.Figlet(font="slant", width=min(term_width - 10, 120))
        ascii_art = fig.renderText(APP_NAME)
    except Exception:
        ascii_art = f"  {APP_NAME}  "
    header_text = Text(ascii_art, style="bold green")
    return Panel(header_text, title=f"v{VERSION}", title_align="right", box=box.ROUNDED)


def print_message(text: str, style: str = "green", prefix: str = "•") -> None:
    console.print(f"[{style}]{prefix} {text}[/{style}]")


def print_error(message: str) -> None:
    print_message(message, "red", "✗")


def print_success(message: str) -> None:
    print_message(message, "green", "✓")


def print_warning(message: str) -> None:
    print_message(message, "yellow", "⚠")


# Async helper to run a shell command
async def run_command_async(cmd: str, timeout: int = 60) -> Tuple[int, str, str]:
    process = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=os.environ.copy(),
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        return process.returncode, stdout.decode().strip(), stderr.decode().strip()
    except asyncio.TimeoutError:
        process.kill()
        return -1, "", "Command timed out."


# Synchronous helper for interactive commands
def run_interactive_command(cmd: str) -> None:
    try:
        subprocess.run(cmd, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print_error(f"Command '{cmd}' failed with error: {e}")


# Main asynchronous installation process
async def main_async() -> None:
    clear_screen()
    console.print(create_header())
    print_message("Starting installation and configuration of Obsidian Livesync on Fly.io...", "cyan")

    # Install prerequisites
    print_message("Installing Fly.io CLI...", "cyan")
    code, out, err = await run_command_async("curl -L https://fly.io/install.sh | sh", timeout=120)
    if code != 0:
        print_error(f"Fly.io CLI installation failed: {err}")
        return
    print_success("Fly.io CLI installed.")

    print_message("Installing Deno...", "cyan")
    code, out, err = await run_command_async("curl -fsSL https://deno.land/x/install/install.sh | sh", timeout=120)
    if code != 0:
        print_error(f"Deno installation failed: {err}")
        return
    print_success("Deno installed.")

    print_message("Updating package list and installing jq...", "cyan")
    code, out, err = await run_command_async("apt update && apt -y install jq", timeout=120)
    if code != 0:
        print_error(f"Failed to update packages or install jq: {err}")
        return
    print_success("System updated and jq installed.")

    # Update PATH environment variable
    fly_bin: str = "/root/.fly/bin"
    deno_bin: str = "/root/.deno/bin"
    os.environ["PATH"] = f"{fly_bin}:{deno_bin}:" + os.environ.get("PATH", "")
    print_success("Updated PATH environment variable.")

    # Clone the repository
    print_message("Cloning Obsidian Livesync repository...", "cyan")
    if not os.path.exists("obsidian-livesync"):
        code, out, err = await run_command_async("git clone --recursive https://github.com/vrtmrz/obsidian-livesync", timeout=180)
        if code != 0:
            print_error(f"Failed to clone repository: {err}")
            return
        print_success("Repository cloned.")
    else:
        print_warning("Repository already exists. Skipping clone.")

    # Flyctl authentication (interactive)
    print_message("Please sign up or log in with Fly.io (an interactive prompt will appear)...", "cyan")
    run_interactive_command("flyctl auth signup")
    print_success("Fly.io authentication completed.")

    # Region selection
    regions = [
        "ams/Amsterdam, Netherlands",
        "arn/Stockholm, Sweden",
        "atl/Atlanta, Georgia (US)",
        "bog/Bogotá, Colombia",
        "bos/Boston, Massachusetts (US)",
        "cdg/Paris, France",
        "den/Denver, Colorado (US)",
        "dfw/Dallas, Texas (US)",
        "ewr/Secaucus, NJ (US)",
        "eze/Ezeiza, Argentina",
        "gdl/Guadalajara, Mexico",
        "gig/Rio de Janeiro, Brazil",
        "gru/Sao Paulo, Brazil",
        "hkg/Hong Kong, Hong Kong",
        "iad/Ashburn, Virginia (US)",
        "jnb/Johannesburg, South Africa",
        "lax/Los Angeles, California (US)",
        "lhr/London, United Kingdom",
        "mad/Madrid, Spain",
        "mia/Miami, Florida (US)",
        "nrt/Tokyo, Japan",
        "ord/Chicago, Illinois (US)",
        "otp/Bucharest, Romania",
        "phx/Phoenix, Arizona (US)",
        "qro/Querétaro, Mexico",
        "scl/Santiago, Chile",
        "sea/Seattle, Washington (US)",
        "sin/Singapore, Singapore",
        "sjc/San Jose, California (US)",
        "syd/Sydney, Australia",
        "waw/Warsaw, Poland",
        "yul/Montreal, Canada",
        "yyz/Toronto, Canada",
    ]
    region_choice: str = Prompt.ask("Select a region", choices=regions, default="nrt/Tokyo, Japan")
    region_code: str = region_choice.split("/")[0]
    os.environ["region"] = region_code
    print_success(f"Region set to: {region_choice} (code: {region_code})")

    # Change to the Fly.io deployment directory
    flyio_path: str = os.path.join("obsidian-livesync", "utils", "flyio")
    try:
        os.chdir(flyio_path)
        print_success(f"Changed directory to {flyio_path}")
    except Exception as e:
        print_error(f"Failed to change directory to {flyio_path}: {e}")
        return

    # Deploy the server using the deploy script
    print_message("Deploying the Obsidian Livesync server on Fly.io...", "cyan")
    deploy_cmd: str = "./deploy-server.sh"
    # Run the deploy script and save its output to deploy-result.txt
    full_deploy_cmd: str = f"{deploy_cmd} | tee deploy-result.txt"
    code, out, err = await run_command_async(full_deploy_cmd, timeout=300)
    if code != 0:
        print_error(f"Deployment failed: {err}")
        return
    print_success("Deployment script executed.")

    # Read the deploy-result.txt file and check the result
    deploy_result_file: str = "deploy-result.txt"
    if not os.path.exists(deploy_result_file):
        print_error("deploy-result.txt not found.")
        return
    try:
        with open(deploy_result_file, "r") as f:
            lines = f.readlines()
            if not lines:
                print_error("deploy-result.txt is empty.")
                return
            last_line: str = lines[-1].strip()
    except Exception as e:
        print_error(f"Error reading deploy-result.txt: {e}")
        return

    if last_line.startswith("obsidian://"):
        print_success("Setup successful! Copy your setup URI and import it into Obsidian.")
        console.print(Panel(last_line, title="Setup URI", style="bold green", box=box.ROUNDED))
    else:
        print_error("Deployment did not return a valid setup URI.")
        console.print(Panel(last_line, title="Deployment Result", style="bold red", box=box.ROUNDED))

    print_message("If you want to delete this instance later, run the delete script: ./delete-server.sh", "cyan")
    print_message("Keep the output secure as it contains your secret memo.", "cyan")


# Async shutdown helpers
async def proper_shutdown_async() -> None:
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


def proper_shutdown() -> None:
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            print_warning("Event loop already running during shutdown")
            return
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(proper_shutdown_async())
    loop.close()


def setup_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda sig=sig: asyncio.create_task(signal_handler_async(sig)))


async def signal_handler_async(sig) -> None:
    print_warning(f"Received signal: {sig}. Initiating shutdown...")
    await proper_shutdown_async()
    asyncio.get_event_loop().stop()


def main() -> None:
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        setup_signal_handlers(loop)
        atexit.register(proper_shutdown)
        loop.run_until_complete(main_async())
    except KeyboardInterrupt:
        print_warning("Keyboard interrupt received. Shutting down...")
    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")
    finally:
        try:
            tasks = asyncio.all_tasks(loop)
            for task in tasks:
                task.cancel()
            if tasks:
                loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
            loop.close()
        except Exception as e:
            print_error(f"Error during shutdown: {e}")
        print_message("Installation process terminated.", "cyan")


if __name__ == "__main__":
    main()