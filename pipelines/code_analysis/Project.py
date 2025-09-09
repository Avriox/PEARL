import logging
import subprocess
import sys
import yaml
import shutil
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any


class Project:
    """Manages a Python project - configuration, environment, and basic execution"""

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.config_path = self.directory / "project-config.yaml"
        self.config = None
        self.venv_path = None
        self.python_executable = None

        logging.info(f"Initializing project from {self.directory}")

        # Load configuration
        self._load_config()

        # Setup virtual environment
        self._setup_venv()

        # Install dependencies
        self._install_dependencies()

    def _load_config(self):
        """Load and parse the YAML configuration file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")

        with open(self.config_path, "r") as f:
            self.config = yaml.safe_load(f)

        # Extract configuration sections
        self.project_info = self.config.get("project", {})
        self.venv_config = self.config.get("venv", {})
        self.dependencies = self.config.get("dependencies", {})
        self.entrypoint = self.config.get("entrypoint", {})
        self.run_config = self.config.get("run", {})

        logging.info(f"Loaded project: {self.project_info.get('name', 'Unknown')}")


    def _setup_venv(self):
        """Create a virtual environment in the project directory."""
        venv_dir = self.venv_config.get("dir", ".venv")
        self.venv_path = (self.directory / venv_dir).resolve()

        # Determine Python executable for venv (don't resolve symlinks for existence check)
        if sys.platform == "win32":
            python_path = self.venv_path / "Scripts" / "python.exe"
        else:
            python_path = self.venv_path / "bin" / "python"

        # Check if venv already exists by checking the symlink itself, not its target
        if self.venv_path.exists() and python_path.exists():
            # Store the symlink path, not the resolved target
            self.python_executable = python_path
            logging.info(f"Virtual environment already exists at {self.venv_path}")
            return

        # Create virtual environment if it doesn't exist
        logging.info(f"Creating virtual environment at {self.venv_path}")

        try:
            subprocess.run(
                [sys.executable, "-m", "venv", str(self.venv_path)],
                cwd=self.directory,
                check=True,
                capture_output=True,
                text=True,
            )
            logging.info("Virtual environment created successfully")

            # Set the python executable path after creation
            self.python_executable = python_path

            # Upgrade pip
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
        # Install profiling tools first
        try:
            subprocess.run(
                [
                    str(self.python_executable),
                    "-m",
                    "pip",
                    "install",
                    "pyinstrument",
                    "line_profiler",
                    "memory_profiler",
                ],
                cwd=self.directory,
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError:
            logging.warning("Some profiling tools may not have installed")

        # Install project requirements
        requirements_files = self.dependencies.get("requirements_files", [])

        if not requirements_files:
            logging.info("No dependencies to install")
            return

        for req_file in requirements_files:
            req_path = self.directory / req_file

            if not req_path.exists():
                logging.warning(f"Requirements file not found: {req_path}")
                continue

            if req_path.stat().st_size == 0:
                logging.info(f"Requirements file {req_file} is empty, skipping")
                continue

            logging.info(f"Installing dependencies from {req_file}")

            try:
                subprocess.run(
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

    def build_entrypoint_info(self, args: Optional[List[str]] = None) -> Dict[str, Any]:
        """Return a dict describing how to run the project's entrypoint."""
        entry_type = self.entrypoint.get("type", "script")
        if entry_type == "script":
            script = self.entrypoint.get("script")
            if not script:
                raise ValueError("Entrypoint type 'script' requires 'script' path")
            script_path = (self.directory / script).resolve()
            argv0 = str(script_path)
            target = str(script_path)
        elif entry_type == "module":
            module = self.entrypoint.get("module")
            if not module:
                raise ValueError("Entrypoint type 'module' requires 'module' name")
            argv0 = module
            target = module
        else:
            raise ValueError(f"Unsupported entry type: {entry_type}")

        ep_args = list(self.entrypoint.get("args", []) or [])
        if args:
            ep_args.extend(args)

        working_dir = (
            self.directory / self.entrypoint.get("working_dir", ".")
        ).resolve()
        env = dict(os.environ)
        env.update(self.entrypoint.get("env", {}) or {})

        return {
            "type": entry_type,
            "argv0": argv0,
            "target": target,
            "args": ep_args,
            "cwd": str(working_dir),
            "env": env,
        }

    def build_run_command(
        self, args: Optional[List[str]] = None
    ) -> Tuple[List[str], str, Dict[str, str]]:
        """Build a subprocess command to run the entrypoint normally."""
        info = self.build_entrypoint_info(args=args)

        if info["type"] == "script":
            cmd = [str(self.python_executable), info["target"]]
        else:
            cmd = [str(self.python_executable), "-m", info["target"]]

        if info["args"]:
            cmd.extend(info["args"])

        return cmd, info["cwd"], info["env"]

    def run_with_profiling(
        self, profiling_code: str, args: Optional[List[str]] = None
    ) -> subprocess.CompletedProcess:
        """Run the project with injected profiling code (wrapper script)."""
        import tempfile

        # Create a wrapper script
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            wrapper_path = f.name
            f.write(profiling_code)

        try:
            # Build command: run the wrapper with the project's Python
            cmd = [str(self.python_executable), wrapper_path]

            # Get working directory and env from entrypoint
            info = self.build_entrypoint_info()
            working_dir = info["cwd"]
            env = info["env"]

            # Run
            result = subprocess.run(
                cmd,
                cwd=str(working_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=self.run_config.get("timeout_seconds", 60),
            )
            return result

        finally:
            # Cleanup wrapper
            Path(wrapper_path).unlink(missing_ok=True)

    def run(self, args: Optional[List[str]] = None) -> subprocess.CompletedProcess:
        """Run the project normally (for warmup)"""
        cmd, working_dir, env = self.build_run_command(args=args)
        return subprocess.run(
            cmd,
            cwd=str(working_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=self.run_config.get("timeout_seconds", 60),
        )

    def cleanup_venv(self):
        """Remove the virtual environment."""
        if self.venv_path and self.venv_path.exists():
            logging.info(f"Removing virtual environment at {self.venv_path}")
            shutil.rmtree(self.venv_path)

    def __repr__(self):
        return f"Project(name={self.project_info.get('name', 'Unknown')}, path={self.directory})"
