# Project.py
import logging
import subprocess
import sys
import time
import yaml
import shutil
import statistics
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from tqdm import tqdm  # You'll need to install this: pip install tqdm


class Project:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.config_path = self.directory / "project-config.yaml"
        self.config = None
        self.venv_path = None
        self.python_executable = None
        self.logs_dir = self.directory / "run_logs"

        logging.info(f"Initializing project from {self.directory}")

        # Create logs directory if it doesn't exist
        self.logs_dir.mkdir(exist_ok=True)

        # Load and parse the YAML configuration
        self._load_config()

        # Setup virtual environment
        self._setup_venv()

        # Install dependencies
        self._install_dependencies()

    def _load_config(self):
        """Load and parse the YAML configuration file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")

        logging.info(f"Loading configuration from {self.config_path}")

        with open(self.config_path, "r") as f:
            self.config = yaml.safe_load(f)

        # Extract key configuration elements
        self.project_info = self.config.get("project", {})
        self.environment = self.config.get("environment", {})
        self.venv_config = self.config.get("venv", {})
        self.dependencies = self.config.get("dependencies", {})
        self.entrypoint = self.config.get("entrypoint", {})
        self.run_config = self.config.get("run", {})

        logging.info(f"Loaded project: {self.project_info.get('name', 'Unknown')}")

    def _setup_venv(self):
        """Create a virtual environment in the project directory."""
        venv_dir = self.venv_config.get("dir", ".venv")
        self.venv_path = self.directory / venv_dir

        # Determine Python executable for venv
        if sys.platform == "win32":
            self.python_executable = self.venv_path / "Scripts" / "python.exe"
            pip_executable = self.venv_path / "Scripts" / "pip.exe"
        else:
            self.python_executable = self.venv_path / "bin" / "python"
            pip_executable = self.venv_path / "bin" / "pip"

        # Check if venv already exists
        if self.venv_path.exists() and self.python_executable.exists():
            logging.info(f"Virtual environment already exists at {self.venv_path}")
            return

        logging.info(f"Creating virtual environment at {self.venv_path}")

        # Create virtual environment
        try:
            subprocess.run(
                [sys.executable, "-m", "venv", str(self.venv_path)],
                cwd=self.directory,
                check=True,
                capture_output=True,
                text=True,
            )
            logging.info("Virtual environment created successfully")

            # Upgrade pip to latest version
            subprocess.run(
                [
                    str(self.python_executable),
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "pip",
                ],
                cwd=self.directory,
                check=True,
                capture_output=True,
                text=True,
            )
            logging.info("Upgraded pip to latest version")

        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to create virtual environment: {e}")
            logging.error(f"stdout: {e.stdout}")
            logging.error(f"stderr: {e.stderr}")
            raise

    def _install_dependencies(self):
        """Install project dependencies in the virtual environment."""
        requirements_files = self.dependencies.get("requirements_files", [])

        if not requirements_files:
            logging.info("No dependencies to install")
            return

        for req_file in requirements_files:
            req_path = self.directory / req_file

            if not req_path.exists():
                logging.warning(f"Requirements file not found: {req_path}")
                continue

            # Check if the file is empty
            if req_path.stat().st_size == 0:
                logging.info(
                    f"Requirements file {req_file} is empty, skipping installation"
                )
                continue

            logging.info(f"Installing dependencies from {req_file}")

            try:
                # Use absolute path to avoid path resolution issues
                result = subprocess.run(
                    [
                        str(self.python_executable),
                        "-m",
                        "pip",
                        "install",
                        "-r",
                        str(req_path.resolve()),
                    ],
                    cwd=self.directory,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                logging.info(f"Successfully installed dependencies from {req_file}")

            except subprocess.CalledProcessError as e:
                logging.error(f"Failed to install dependencies: {e}")
                logging.error(f"stdout: {e.stdout}")
                logging.error(f"stderr: {e.stderr}")
                raise

    def _build_run_command(self, custom_args: Optional[List[str]] = None) -> List[str]:
        """Build the command to run the project."""
        cmd = [str(self.python_executable)]

        # Add Python options if specified
        python_opts = self.entrypoint.get("python_opts", [])
        cmd.extend(python_opts)

        # Determine what to run based on entrypoint type
        entry_type = self.entrypoint.get("type", "script")

        if entry_type == "script":
            script = self.entrypoint.get("script")
            if script:
                # Use absolute path for the script
                script_path = (self.directory / script).resolve()
                cmd.append(str(script_path))
        elif entry_type == "module":
            module = self.entrypoint.get("module")
            if module:
                cmd.extend(["-m", module])
        elif entry_type == "callable":
            callable_spec = self.entrypoint.get("callable")
            if callable_spec:
                # For callable, we'd need a wrapper script
                # This is a simplified version
                cmd.extend(
                    [
                        "-c",
                        f"from {callable_spec.split(':')[0]} import {callable_spec.split(':')[1]}; {callable_spec.split(':')[1]}()",
                    ]
                )

        # Add arguments
        if custom_args:
            cmd.extend(custom_args)
        else:
            default_args = self.run_config.get("default_args", [])
            cmd.extend(default_args)

        return cmd

    def _create_log_file(self, run_type: str = "single") -> Path:
        """Create a unique log file for this run."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[
            :-3
        ]  # milliseconds precision
        log_filename = f"{run_type}_run_{timestamp}.log"
        return self.logs_dir / log_filename

    def run(
        self,
        custom_args: Optional[List[str]] = None,
        timeout: Optional[float] = None,
        log_output: bool = True,
        silent: bool = True,
    ) -> Tuple[float, subprocess.CompletedProcess, Optional[Path]]:
        """
        Run the project in an isolated subprocess.

        Args:
            custom_args: Custom arguments to pass to the program
            timeout: Timeout in seconds (uses config default if not specified)
            log_output: Whether to save output to a log file
            silent: Whether to suppress non-error output in console

        Returns:
            Tuple of (execution_time, subprocess.CompletedProcess, log_file_path)
        """
        cmd = self._build_run_command(custom_args)

        # Get working directory (use absolute path)
        working_dir = (
            self.directory / self.entrypoint.get("working_dir", ".")
        ).resolve()

        # Get environment variables
        env = dict(os.environ)
        env.update(self.entrypoint.get("env", {}))

        # Get timeout
        if timeout is None:
            timeout = self.run_config.get("timeout_seconds", 60)

        # Create log file if needed
        log_file = None
        if log_output:
            log_file = self._create_log_file("single")

        if not silent:
            logging.info(f"Running command: {' '.join(cmd)}")
            logging.info(f"Working directory: {working_dir}")
            if log_file:
                logging.info(
                    f"Output will be saved to: {log_file.relative_to(self.directory)}"
                )

        try:
            # Use perf_counter for high-precision timing
            start_time = time.perf_counter()

            result = subprocess.run(
                cmd,
                cwd=str(working_dir),
                env=env,
                capture_output=True,  # Always capture to handle it ourselves
                text=True,
                timeout=timeout,
                check=False,  # Don't raise on non-zero exit
            )

            end_time = time.perf_counter()
            execution_time = end_time - start_time

            # Write output to log file if requested
            if log_file:
                with open(log_file, "w") as f:
                    f.write(f"Command: {' '.join(cmd)}\n")
                    f.write(f"Working Directory: {working_dir}\n")
                    f.write(f"Execution Time: {execution_time:.4f} seconds\n")
                    f.write(f"Return Code: {result.returncode}\n")
                    f.write(f"{'='*60}\n")
                    f.write("STDOUT:\n")
                    f.write(result.stdout)
                    f.write(f"\n{'='*60}\n")
                    f.write("STDERR:\n")
                    f.write(result.stderr)

            if result.returncode != 0:
                # Always log errors to console
                logging.error(f"Process exited with code {result.returncode}")
                if result.stderr:
                    logging.error(
                        f"Error output: {result.stderr[:500]}"
                    )  # First 500 chars
                if log_file:
                    logging.error(
                        f"Full output saved to: {log_file.relative_to(self.directory)}"
                    )
            elif not silent:
                logging.info(
                    f"Process completed successfully in {execution_time:.4f} seconds"
                )

            return execution_time, result, log_file

        except subprocess.TimeoutExpired as e:
            logging.error(f"Process timed out after {timeout} seconds")
            if log_file:
                with open(log_file, "w") as f:
                    f.write(f"Command: {' '.join(cmd)}\n")
                    f.write(f"Process timed out after {timeout} seconds\n")
            raise
        except Exception as e:
            logging.error(f"Error running process: {e}")
            raise

    def run_multiple(
        self,
        runs: int = 5,
        custom_args: Optional[List[str]] = None,
        warmup_runs: int = 1,
        timeout: Optional[float] = None,
        save_logs: bool = True,
        show_progress: bool = True,
    ) -> Dict[str, Any]:
        """
        Run the project multiple times and collect timing statistics.

        Args:
            runs: Number of measurement runs
            custom_args: Custom arguments to pass to the program
            warmup_runs: Number of warmup runs (not included in statistics)
            timeout: Timeout per run in seconds
            save_logs: Whether to save output logs for each run
            show_progress: Whether to show a progress bar

        Returns:
            Dictionary with timing statistics
        """
        project_name = self.project_info.get("name", "Unknown")

        # Create a subdirectory for this batch of runs
        if save_logs:
            batch_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            batch_dir = self.logs_dir / f"batch_{batch_timestamp}"
            batch_dir.mkdir(exist_ok=True)
            # Temporarily change logs dir
            original_logs_dir = self.logs_dir
            self.logs_dir = batch_dir

        logging.info(
            f"Starting multiple runs for {project_name}: {warmup_runs} warmup, {runs} measurement"
        )

        # Warmup runs
        if warmup_runs > 0:
            if show_progress:
                warmup_bar = tqdm(
                    range(warmup_runs),
                    desc=f"{project_name} - Warmup",
                    bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt}",
                )
            else:
                warmup_bar = range(warmup_runs)

            for i in warmup_bar:
                try:
                    # Don't save logs for warmup runs
                    self.run(
                        custom_args, timeout=timeout, log_output=False, silent=True
                    )
                except Exception as e:
                    logging.warning(f"Warmup run {i + 1} failed: {e}")

        # Measurement runs
        execution_times = []
        successful_runs = 0
        failed_runs = 0
        log_files = []

        if show_progress:
            measurement_bar = tqdm(
                range(runs),
                desc=f"{project_name} - Measurement",
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
            )
        else:
            measurement_bar = range(runs)

        for i in measurement_bar:
            try:
                exec_time, result, log_file = self.run(
                    custom_args, timeout=timeout, log_output=save_logs, silent=True
                )

                if result.returncode == 0:
                    execution_times.append(exec_time)
                    successful_runs += 1
                    if log_file:
                        log_files.append(log_file)
                else:
                    failed_runs += 1

            except Exception as e:
                failed_runs += 1
                logging.error(f"Run {i + 1} failed with exception: {e}")

        # Restore original logs dir
        if save_logs:
            self.logs_dir = original_logs_dir

        if not execution_times:
            raise RuntimeError("No successful runs completed")

        # Calculate statistics
        stats = {
            "project_id": self.project_info.get("id", "unknown"),
            "project_name": project_name,
            "total_runs": runs,
            "successful_runs": successful_runs,
            "failed_runs": failed_runs,
            "execution_times": execution_times,
            "mean": statistics.mean(execution_times),
            "median": statistics.median(execution_times),
            "stdev": (
                statistics.stdev(execution_times) if len(execution_times) > 1 else 0
            ),
            "min": min(execution_times),
            "max": max(execution_times),
            "arguments": custom_args or self.run_config.get("default_args", []),
            "log_directory": (
                str(batch_dir.relative_to(self.directory)) if save_logs else None
            ),
        }

        # Summary output
        logging.info(f"{'='*60}")
        logging.info(
            f"Completed {successful_runs}/{runs} successful runs for {project_name}"
        )
        logging.info(f"Mean execution time: {stats['mean']:.4f}s")
        logging.info(f"Median execution time: {stats['median']:.4f}s")
        logging.info(f"Std deviation: {stats['stdev']:.4f}s")
        logging.info(f"Min/Max: {stats['min']:.4f}s / {stats['max']:.4f}s")
        if save_logs and batch_dir:
            logging.info(f"Logs saved to: {batch_dir.relative_to(self.directory)}")
        logging.info(f"{'='*60}")

        return stats

    def get_performance_issues(self) -> List[Dict[str, Any]]:
        """Get the list of performance issues from the configuration."""
        return self.project_info.get("performance_issues", [])

    def cleanup_venv(self):
        """Remove the virtual environment."""
        if self.venv_path and self.venv_path.exists():
            logging.info(f"Removing virtual environment at {self.venv_path}")
            shutil.rmtree(self.venv_path)

    def cleanup_logs(self):
        """Remove all log files."""
        if self.logs_dir and self.logs_dir.exists():
            logging.info(f"Removing logs directory at {self.logs_dir}")
            shutil.rmtree(self.logs_dir)
            self.logs_dir.mkdir(exist_ok=True)  # Recreate empty directory

    def __repr__(self):
        return f"Project(name={self.project_info.get('name', 'Unknown')}, path={self.directory})"
