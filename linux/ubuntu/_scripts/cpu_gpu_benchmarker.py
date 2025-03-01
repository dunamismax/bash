#!/usr/bin/env python3
"""
CPU and GPU Benchmark Tool

This utility benchmarks your system's CPU and GPU performance:
  • CPU performance is stressed via prime number calculations.
  • GPU performance is evaluated using NumPy matrix multiplications.
  
The tool provides a Nord‑themed CLI interface with interactive progress indicators,
clear feedback messages, and striking ASCII art headers. Designed for Ubuntu/Linux,
it leverages Rich, Click, and pyfiglet for an elegant command‑line experience.

Required Packages:
  • click
  • rich
  • pyfiglet
  • psutil
  • numpy
  • GPUtil3
"""

import atexit
import os
import signal
import sys
import time
import threading
import traceback

import click
import psutil
import numpy as np
import GPUtil
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
import pyfiglet

# ------------------------------
# Configuration
# ------------------------------
DEFAULT_BENCHMARK_DURATION = 10  # seconds
VERSION = "1.0.0"

# ------------------------------
# Nord‑Themed Styles & Console Setup
# ------------------------------
# Nord color palette examples:
# nord0: #2E3440, nord1: #3B4252, nord4: #D8DEE9, nord8: #88C0D0, nord10: #5E81AC, nord11: #BF616A, nord14: #A3BE8C

console = Console()

def print_header(text: str) -> None:
    """Print a pretty ASCII art header using pyfiglet with Nord‑themed style."""
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
# Signal Handling & Cleanup
# ------------------------------
def cleanup() -> None:
    """Perform cleanup tasks before exit."""
    print_step("Performing cleanup tasks...")
    # Add additional cleanup steps if necessary

def signal_handler(sig, frame) -> None:
    """Handle termination signals gracefully."""
    sig_name = "SIGINT" if sig == signal.SIGINT else "SIGTERM"
    print_warning(f"Process interrupted by {sig_name}. Cleaning up...")
    cleanup()
    sys.exit(128 + sig)

atexit.register(cleanup)
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ------------------------------
# Benchmark Functions
# ------------------------------
def is_prime(n: int) -> bool:
    """
    Check if a number is prime.

    Args:
        n (int): Number to check.
    Returns:
        bool: True if prime, False otherwise.
    """
    if n <= 1:
        return False
    if n <= 3:
        return True
    if n % 2 == 0 or n % 3 == 0:
        return False
    i = 5
    while i * i <= n:
        if n % i == 0 or n % (i + 2) == 0:
            return False
        i += 6
    return True

def cpu_prime_benchmark(benchmark_duration: int) -> dict:
    """
    Benchmark CPU performance by calculating prime numbers.

    Args:
        benchmark_duration (int): Duration in seconds.
    Returns:
        dict: {'primes_per_sec': float, 'elapsed_time': float}
    """
    start_time = time.time()
    end_time = start_time + benchmark_duration
    prime_count = 0
    num = 2
    while time.time() < end_time:
        if is_prime(num):
            prime_count += 1
        num += 1
    elapsed = time.time() - start_time
    return {'primes_per_sec': prime_count / elapsed if elapsed > 0 else 0, 'elapsed_time': elapsed}

def get_cpu_info() -> dict:
    """
    Retrieve detailed CPU information.

    Returns:
        dict: {'cores': int, 'threads': int, 'frequency_current': float, 'usage': float}
    """
    freq = psutil.cpu_freq()
    usage = psutil.cpu_percent(interval=None)
    cores = psutil.cpu_count(logical=False)
    threads = psutil.cpu_count(logical=True)
    return {
        'cores': cores,
        'threads': threads,
        'frequency_current': freq.current if freq else 0,
        'usage': usage
    }

def cpu_benchmark(benchmark_duration: int = DEFAULT_BENCHMARK_DURATION) -> dict:
    """
    Run a comprehensive CPU benchmark.

    Args:
        benchmark_duration (int): Duration of the benchmark in seconds.
    Returns:
        dict: Merged results from prime benchmark and CPU info.
    """
    with console.status(f"[bold #81A1C1]Running CPU benchmark for {benchmark_duration} seconds...", spinner="dots"):
        prime_results = cpu_prime_benchmark(benchmark_duration)
    cpu_info = get_cpu_info()
    return {**prime_results, **cpu_info}

def gpu_matrix_benchmark(benchmark_duration: int) -> dict:
    """
    Benchmark GPU performance via matrix multiplication using NumPy.

    Args:
        benchmark_duration (int): Duration in seconds.
    Returns:
        dict: {'iterations_per_sec': float, 'elapsed_time': float, 'gpu_object': GPU info} or error message.
    """
    try:
        gpus = GPUtil.getGPUs()
        if not gpus:
            return {'error': 'No GPUs detected. Ensure drivers are installed and GPUtil is working correctly.'}
        gpu = gpus[0]  # Use the first GPU
    except Exception as e:
        return {'error': f'Error retrieving GPU info: {e}'}
    
    matrix_size = 1024
    A = np.random.rand(matrix_size, matrix_size).astype(np.float32)
    B = np.random.rand(matrix_size, matrix_size).astype(np.float32)
    iterations = 0
    start_time = time.time()
    end_time = start_time + benchmark_duration
    while time.time() < end_time:
        np.dot(A, B)
        iterations += 1
    elapsed = time.time() - start_time
    return {'iterations_per_sec': iterations / elapsed if elapsed > 0 else 0, 'elapsed_time': elapsed, 'gpu_object': gpu}

def get_gpu_info_from_benchmark(result: dict) -> dict:
    """
    Extract relevant GPU details from the benchmark result.

    Args:
        result (dict): Result from gpu_matrix_benchmark.
    Returns:
        dict: GPU details or error message.
    """
    if 'error' in result:
        return result
    gpu = result['gpu_object']
    return {
        'name': gpu.name,
        'load': gpu.load * 100,
        'memory_util': gpu.memoryUtil * 100,
        'temperature': gpu.temperature
    }

def gpu_benchmark(benchmark_duration: int = DEFAULT_BENCHMARK_DURATION) -> dict:
    """
    Run a comprehensive GPU benchmark.

    Args:
        benchmark_duration (int): Duration of the benchmark in seconds.
    Returns:
        dict: Merged GPU benchmark results and GPU information.
    """
    with console.status(f"[bold #81A1C1]Running GPU benchmark for {benchmark_duration} seconds...", spinner="dots"):
        gpu_results = gpu_matrix_benchmark(benchmark_duration)
    if 'error' in gpu_results:
        return gpu_results
    gpu_info = get_gpu_info_from_benchmark(gpu_results)
    return {**gpu_results, **gpu_info}

# ------------------------------
# Output and Display Functions
# ------------------------------
def display_cpu_results(results: dict) -> None:
    """Display formatted CPU benchmark results."""
    print_header("CPU Benchmark Results")
    console.print(f"CPU Cores (Physical): [bold #88C0D0]{results['cores']}[/bold #88C0D0]")
    console.print(f"CPU Threads (Logical): [bold #88C0D0]{results['threads']}[/bold #88C0D0]")
    console.print(f"CPU Frequency (Current): [bold #88C0D0]{results['frequency_current']:.2f} MHz[/bold #88C0D0]")
    console.print(f"CPU Usage during Benchmark: [bold #88C0D0]{results['usage']:.2f}%[/bold #88C0D0]")
    console.print(f"Benchmark Duration: [bold #88C0D0]{results['elapsed_time']:.2f} seconds[/bold #88C0D0]")
    console.print(f"[bold #8FBCBB]✓ Prime Numbers per Second: {results['primes_per_sec']:.2f}[/bold #8FBCBB]")
    console.print("\n[bold #88C0D0]Benchmark Details:[/bold #88C0D0]")
    console.print("- Prime number calculation is used to stress the CPU.")

def display_gpu_results(results: dict) -> None:
    """Display formatted GPU benchmark results."""
    if 'error' in results:
        print_error("GPU Benchmark Error")
        console.print(f"[bold #BF616A]{results['error']}[/bold #BF616A]")
        console.print("\n[bold #5E81AC]Troubleshooting Tips:[/bold #5E81AC]")
        console.print("- Ensure GPU drivers are installed correctly.")
        console.print("- Verify that GPUtil3 is installed (pip install GPUtil3).")
        console.print("- For more intensive benchmarks, consider using libraries like CuPy or TensorFlow.")
    else:
        print_header("GPU Benchmark Results")
        console.print(f"GPU Name: [bold #88C0D0]{results['name']}[/bold #88C0D0]")
        console.print(f"Benchmark Duration: [bold #88C0D0]{results['elapsed_time']:.2f} seconds[/bold #88C0D0]")
        console.print(f"[bold #8FBCBB]✓ Matrix Multiplications per Second: {results['iterations_per_sec']:.2f}[/bold #8FBCBB]")
        console.print(f"GPU Load during Benchmark: [bold #88C0D0]{results['load']:.2f}%[/bold #88C0D0]")
        console.print(f"GPU Memory Utilization: [bold #88C0D0]{results['memory_util']:.2f}%[/bold #88C0D0]")
        console.print(f"GPU Temperature: [bold #88C0D0]{results['temperature']:.2f}°C[/bold #88C0D0]")
        console.print("\n[bold #88C0D0]Benchmark Details:[/bold #88C0D0]")
        console.print("- Matrix multiplication (NumPy) is used as the workload.")
        console.print("- GPU utilization may vary based on system configuration.")

# ------------------------------
# CLI Commands with Click
# ------------------------------
@click.group()
@click.version_option(version=VERSION)
def cli() -> None:
    """
    CPU and GPU Benchmark Tool - Nord Themed CLI

    Benchmark your system's performance using CPU prime calculations and GPU matrix multiplications.
    """
    pass

@cli.command()
@click.option('--duration', default=DEFAULT_BENCHMARK_DURATION, type=int,
              help='Duration of the CPU benchmark in seconds.', metavar='SECONDS')
def cpu(duration: int) -> None:
    """Run CPU benchmark."""
    print_header("Starting CPU Benchmark")
    try:
        results = cpu_benchmark(duration)
        display_cpu_results(results)
        print_success("CPU Benchmark Completed")
    except Exception as e:
        print_error(f"Error during CPU benchmark: {e}")
        traceback.print_exc()

@cli.command()
@click.option('--duration', default=DEFAULT_BENCHMARK_DURATION, type=int,
              help='Duration of the GPU benchmark in seconds.', metavar='SECONDS')
def gpu(duration: int) -> None:
    """Run GPU benchmark."""
    print_header("Starting GPU Benchmark")
    try:
        results = gpu_benchmark(duration)
        display_gpu_results(results)
        print_success("GPU Benchmark Completed")
    except Exception as e:
        print_error(f"Error during GPU benchmark: {e}")
        traceback.print_exc()

@cli.command()
@click.option('--duration', default=DEFAULT_BENCHMARK_DURATION, type=int,
              help='Duration of both benchmarks in seconds.', metavar='SECONDS')
def both(duration: int) -> None:
    """Run both CPU and GPU benchmarks concurrently."""
    print_header("Starting CPU and GPU Benchmarks")
    cpu_results = {}
    gpu_results = {}

    def run_cpu() -> None:
        nonlocal cpu_results
        cpu_results = cpu_benchmark(duration)

    def run_gpu() -> None:
        nonlocal gpu_results
        gpu_results = gpu_benchmark(duration)

    cpu_thread = threading.Thread(target=run_cpu)
    gpu_thread = threading.Thread(target=run_gpu)
    cpu_thread.start()
    gpu_thread.start()
    cpu_thread.join()
    gpu_thread.join()

    display_cpu_results(cpu_results)
    display_gpu_results(gpu_results)
    print_success("CPU and GPU Benchmarks Completed")

@cli.command()
def menu() -> None:
    """Interactive menu to select and run benchmarks."""
    while True:
        print_header("Benchmark Menu")
        console.print("[bold #88C0D0]Select a benchmark to run:[/bold #88C0D0]")
        console.print("[bold #88C0D0]1.[/bold #88C0D0] CPU Benchmark")
        console.print("[bold #88C0D0]2.[/bold #88C0D0] GPU Benchmark")
        console.print("[bold #88C0D0]3.[/bold #88C0D0] CPU and GPU Benchmarks")
        console.print("[bold #88C0D0]4.[/bold #88C0D0] Exit")
        try:
            choice = click.prompt("[bold #88C0D0]Enter your choice [1-4][/bold #88C0D0]", type=click.IntRange(1, 4))
        except Exception as e:
            print_error(f"Invalid input: {e}")
            continue

        ctx = click.get_current_context()
        if choice == 1:
            ctx.invoke(cpu)
        elif choice == 2:
            ctx.invoke(gpu)
        elif choice == 3:
            ctx.invoke(both)
        elif choice == 4:
            console.print("[bold #88C0D0]Exiting Benchmark Tool...[/bold #88C0D0]")
            break
        else:
            print_error("Invalid choice. Please select from 1-4.")

# ------------------------------
# Main Execution
# ------------------------------
if __name__ == '__main__':
    try:
        cli()
    except Exception as e:
        print_error(f"Unhandled error: {e}")
        traceback.print_exc()
        sys.exit(1)