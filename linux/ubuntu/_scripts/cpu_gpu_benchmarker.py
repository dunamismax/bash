#!/usr/bin/env python3

import click
import psutil
import time
import threading
import numpy as np
import GPUtil  # Requires 'pip install GPUtil3' - note the '3'

#####################################
# Improved Nord-Themed ANSI Colors for CLI Output with Click
#####################################

class NordTheme:
    """
    Nord color palette for Click CLI output.

    Provides static methods to style text using the Nord color scheme for headers,
    information, success messages, warnings, errors, and bold text.
    """
    nord0 = '#2e3440'  # Polar Night - Darkest
    nord1 = '#3b4252'  # Polar Night - Darker
    nord2 = '#434c5e'  # Polar Night - Dark
    nord3 = '#4c566a'  # Polar Night - Light
    nord4 = '#d8dee9'  # Snow Storm - Lightest
    nord5 = '#e5e9f0'  # Snow Storm - Lighter
    nord6 = '#eceff4'  # Snow Storm - Lightest
    nord7 = '#8fbcbb'  # Frost - Blueish Green
    nord8 = '#88c0d0'  # Frost - Light Blue
    nord9 = '#81a1c1'  # Frost - Sky Blue
    nord10 = '#5e81ac' # Frost - Navy Blue
    nord11 = '#bf616a' # Aurora - Red
    nord12 = '#d08770' # Aurora - Orange
    nord13 = '#ebcb8b' # Aurora - Yellow
    nord14 = '#a3be8c' # Aurora - Green
    nord15 = '#b48ead' # Aurora - Purple

    @staticmethod
    def header(text):
        """Styles text as a header."""
        return click.style(text, fg=NordTheme.nord4, bold=True)

    @staticmethod
    def info(text):
        """Styles text as informational."""
        return click.style(text, fg=NordTheme.nord8)

    @staticmethod
    def success(text):
        """Styles text as a success message."""
        return click.style(text, fg=NordTheme.nord14, bold=True)

    @staticmethod
    def warning(text):
        """Styles text as a warning message."""
        return click.style(text, fg=NordTheme.nord13)

    @staticmethod
    def error(text):
        """Styles text as an error message."""
        return click.style(text, fg=NordTheme.nord11, bold=True)

    @staticmethod
    def bold(text):
        """Styles text as bold."""
        return click.style(text, bold=True)

#####################################
# Benchmark Functions - Improved Modularity and Readability
#####################################

def is_prime(n):
    """
    Efficiently checks if a number is prime.

    Args:
        n (int): The number to check for primality.

    Returns:
        bool: True if the number is prime, False otherwise.
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

def cpu_prime_benchmark(benchmark_duration):
    """
    Benchmarks CPU performance by calculating prime numbers.

    Args:
        benchmark_duration (int): Duration of the benchmark in seconds.

    Returns:
        dict: Dictionary containing benchmark results (elapsed_time, primes_per_sec).
    """
    start_time = time.time()
    end_time = start_time + benchmark_duration
    prime_numbers_found = 0
    number = 2

    while time.time() < end_time:
        if is_prime(number):
            prime_numbers_found += 1
        number += 1

    elapsed_time = time.time() - start_time
    primes_per_sec = prime_numbers_found / elapsed_time if elapsed_time > 0 else 0
    return {'primes_per_sec': primes_per_sec, 'elapsed_time': elapsed_time}


def get_cpu_info():
    """
    Retrieves detailed CPU information using psutil.

    Returns:
        dict: Dictionary containing CPU information (cores, threads, frequency, usage).
    """
    cpu_freq = psutil.cpu_freq()
    cpu_usage = psutil.cpu_percent(interval=None)
    cores = psutil.cpu_count(logical=False)
    threads = psutil.cpu_count(logical=True)
    return {
        'cores': cores,
        'threads': threads,
        'frequency_current': cpu_freq.current,
        'usage': cpu_usage
    }


def cpu_benchmark(benchmark_duration=10):
    """
    Runs a comprehensive CPU benchmark.

    Args:
        benchmark_duration (int): Duration of the benchmark in seconds.

    Returns:
        dict: Dictionary containing CPU benchmark results and CPU information.
    """
    cpu_results = cpu_prime_benchmark(benchmark_duration)
    cpu_info = get_cpu_info()
    return {**cpu_results, **cpu_info} # Merges both dictionaries


def gpu_matrix_benchmark(benchmark_duration):
    """
    Benchmarks GPU performance by performing matrix multiplications using NumPy.
    Note: NumPy may not fully utilize the GPU unless configured with a GPU-backed BLAS library.
    For optimal GPU benchmarking, consider libraries like CuPy or TensorFlow.

    Args:
        benchmark_duration (int): Duration of the benchmark in seconds.

    Returns:
        dict: Dictionary containing benchmark results (iterations_per_sec, elapsed_time).
              Returns an error message if no GPUs are detected or if GPUtil fails.
    """
    try:
        gpus = GPUtil.getGPUs()
        if not gpus:
            return {'error': 'No GPUs detected by GPUtil. Ensure drivers are installed and GPUtil is working correctly.'}
        gpu = gpus[0] # Use the first GPU if multiple are present
    except Exception as e:
        return {'error': f'Error retrieving GPU info: {e}. Is GPUtil installed correctly? Error details: {e}'}

    start_time = time.time()
    end_time = start_time + benchmark_duration
    iterations = 0
    matrix_size = 1024  # Consider making matrix_size configurable if needed in future

    A = np.random.rand(matrix_size, matrix_size).astype(np.float32)
    B = np.random.rand(matrix_size, matrix_size).astype(np.float32)

    while time.time() < end_time:
        np.dot(A, B) # Matrix multiplication
        iterations += 1

    elapsed_time = time.time() - start_time
    iterations_per_sec = iterations / elapsed_time if elapsed_time > 0 else 0
    return {'iterations_per_sec': iterations_per_sec, 'elapsed_time': elapsed_time, 'gpu_object': gpu} # Return gpu object for more details later


def get_gpu_info_from_benchmark(gpu_benchmark_result):
    """
    Extracts relevant GPU information from the GPU benchmark result and GPUtil object.

    Args:
        gpu_benchmark_result (dict): Result dictionary from gpu_matrix_benchmark.

    Returns:
        dict: Dictionary containing GPU information (name, load, memory_util, temp).
              Returns an error dictionary if input is an error result.
    """
    if 'error' in gpu_benchmark_result:
        return gpu_benchmark_result # Propagate error

    gpu = gpu_benchmark_result['gpu_object']
    return {
        'name': gpu.name,
        'load': gpu.load * 100,
        'memory_util': gpu.memoryUtil * 100,
        'temperature': gpu.temperature
    }


def gpu_benchmark(benchmark_duration=10):
    """
    Runs a comprehensive GPU benchmark.

    Args:
        benchmark_duration (int): Duration of the benchmark in seconds.

    Returns:
        dict: Dictionary containing GPU benchmark results and GPU information.
    """
    gpu_results = gpu_matrix_benchmark(benchmark_duration)
    if 'error' in gpu_results:
        return gpu_results # Return error directly
    gpu_info = get_gpu_info_from_benchmark(gpu_results)
    return {**gpu_results, **gpu_info} # Merge benchmark results and GPU info


#####################################
# Output and Display Functions - Improved Clarity and Information
#####################################

def display_cpu_results(results):
    """Displays CPU benchmark results in a formatted output."""
    click.echo(NordTheme.header("\n--- CPU Benchmark Results ---"))
    click.echo(NordTheme.info(f"CPU Cores (Physical): {results['cores']}"))
    click.echo(NordTheme.info(f"CPU Threads (Logical): {results['threads']}"))
    click.echo(NordTheme.info(f"CPU Frequency (Current): {results['frequency_current']:.2f} MHz"))
    click.echo(NordTheme.info(f"CPU Usage during Benchmark: {results['usage']:.2f}%"))
    click.echo(NordTheme.info(f"Benchmark Duration: {results['elapsed_time']:.2f} seconds"))
    click.echo(NordTheme.success(f"Prime Numbers Calculated per Second: {results['primes_per_sec']:.2f}"))
    click.echo(NordTheme.info("\n--- Benchmark Details ---"))
    click.echo(NordTheme.info("- Prime number calculation is used to stress the CPU."))

def display_gpu_results(results):
    """Displays GPU benchmark results in a formatted output."""
    if 'error' in results:
        click.echo(NordTheme.error(f"\n--- GPU Benchmark Error ---"))
        click.echo(NordTheme.error(results['error']))
        click.echo(NordTheme.warning("\n--- Troubleshooting Tips ---"))
        click.echo(NordTheme.warning("- Ensure NVIDIA or AMD drivers are correctly installed."))
        click.echo(NordTheme.warning("- Verify that 'GPUtil3' is installed: `pip install GPUtil3`."))
        click.echo(NordTheme.warning("- For more intensive GPU benchmarks, consider using libraries like CuPy or TensorFlow."))

    else:
        click.echo(NordTheme.header("\n--- GPU Benchmark Results ---"))
        click.echo(NordTheme.info(f"GPU Name: {results['name']}"))
        click.echo(NordTheme.info(f"Benchmark Duration: {results['elapsed_time']:.2f} seconds"))
        click.echo(NordTheme.success(f"Matrix Multiplications per Second: {results['iterations_per_sec']:.2f}"))
        click.echo(NordTheme.info(f"GPU Load during Benchmark: {results['load']:.2f}%"))
        click.echo(NordTheme.info(f"GPU Memory Utilized: {results['memory_util']:.2f}%"))
        click.echo(NordTheme.info(f"GPU Temperature: {results['temperature']:.2f}°C"))
        click.echo(NordTheme.info("\n--- Benchmark Details ---"))
        click.echo(NordTheme.info("- Matrix multiplication (NumPy) is used as a workload."))
        click.echo(NordTheme.info("- GPU utilization might vary based on system configuration and libraries."))
        click.echo(NordTheme.warning("- For more accurate and intensive GPU benchmarks, consider libraries like CuPy or TensorFlow."))


#####################################
# Click CLI Menu - Enhanced with Options and Help Text
#####################################

@click.group()
@click.version_option()
def cli():
    """
    CPU and GPU Benchmark Tool - Nord Theme CLI

    This tool allows you to benchmark your CPU and GPU performance.
    You can run individual benchmarks or both concurrently.
    Use the 'menu' command for an interactive selection.
    """
    pass

@cli.command()
@click.option('--duration', default=10, type=int, help='Duration of the CPU benchmark in seconds.', metavar='SECONDS')
def cpu(duration):
    """Run CPU benchmark for a specified duration."""
    click.echo(NordTheme.header("Starting CPU Benchmark..."))
    results = cpu_benchmark(duration)
    display_cpu_results(results)
    click.echo(NordTheme.success("\nCPU Benchmark Completed."))

@cli.command()
@click.option('--duration', default=10, type=int, help='Duration of the GPU benchmark in seconds.', metavar='SECONDS')
def gpu(duration):
    """Run GPU benchmark for a specified duration."""
    click.echo(NordTheme.header("Starting GPU Benchmark..."))
    results = gpu_benchmark(duration)
    display_gpu_results(results)
    click.echo(NordTheme.success("\nGPU Benchmark Completed."))

@cli.command()
@click.option('--duration', default=10, type=int, help='Duration of both benchmarks in seconds.', metavar='SECONDS')
def both(duration):
    """Run both CPU and GPU benchmarks concurrently for a specified duration."""
    click.echo(NordTheme.header("Starting CPU and GPU Benchmarks..."))

    cpu_results = {}
    gpu_results = {}

    def run_cpu():
        nonlocal cpu_results
        cpu_results = cpu_benchmark(duration)

    def run_gpu():
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
    click.echo(NordTheme.success("\nCPU and GPU Benchmarks Completed."))

@cli.command()
def menu():
    """Interactive menu to select and run benchmarks."""
    while True:
        click.echo(NordTheme.header("\n--- Benchmark Menu ---"))
        click.echo(NordTheme.info("Select benchmark to run:"))
        click.echo(NordTheme.bold("1.") + NordTheme.info(" CPU Benchmark"))
        click.echo(NordTheme.bold("2.") + NordTheme.info(" GPU Benchmark"))
        click.echo(NordTheme.bold("3.") + NordTheme.info(" CPU and GPU Benchmarks"))
        click.echo(NordTheme.bold("4.") + NordTheme.info(" Exit"))

        choice = click.prompt(NordTheme.info("Enter your choice [1-4]"), type=click.IntRange(1, 4), prompt_suffix=NordTheme.info(":"))

        if choice == 1:
            click.invoke(cpu) # Uses default duration
        elif choice == 2:
            click.invoke(gpu) # Uses default duration
        elif choice == 3:
            click.invoke(both) # Uses default duration
        elif choice == 4:
            click.echo(NordTheme.info("Exiting Benchmark Tool."))
            break
        else:
            click.echo(NordTheme.error("Invalid choice. Please select from 1-4."))


#####################################
# Main Execution
#####################################

if __name__ == '__main__':
    cli()