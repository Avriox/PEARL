# ProjectHasher.py
import hashlib
import logging
from pathlib import Path
from typing import List, Set
import json


class ProjectHasher:
    """Compute a hash of a project's content"""

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)

    def compute_project_hash(self) -> str:
        """Compute a hash representing the current state of the project"""
        hasher = hashlib.sha256()

        # Get all relevant files
        py_files = sorted(self.project_root.rglob("*.py"))
        requirements_files = sorted(self.project_root.glob("*requirements*.txt"))
        config_files = sorted(self.project_root.glob("*.yaml")) + sorted(
            self.project_root.glob("*.yml")
        )

        # Filter out venv and cache directories
        py_files = [f for f in py_files if not self._should_ignore(f)]

        # Hash Python files
        for py_file in py_files:
            self._hash_file(hasher, py_file, include_path=True)

        # Hash requirements files
        for req_file in requirements_files:
            self._hash_file(hasher, req_file, include_path=True)

        # Hash config files
        for config_file in config_files:
            self._hash_file(hasher, config_file, include_path=True)

        # Include count of files in hash (to detect file additions/deletions)
        file_count = len(py_files) + len(requirements_files) + len(config_files)
        hasher.update(f"file_count:{file_count}".encode())

        # Get final hash
        return hasher.hexdigest()

    def _should_ignore(self, path: Path) -> bool:
        """Check if a path should be ignored"""
        ignore_patterns = {
            ".venv",
            "__pycache__",
            ".git",
            ".pytest_cache",
            "venv",
            "env",
            ".env",
            "build",
            "dist",
            "*.egg-info",
            "run_logs",
        }

        path_str = str(path)
        for pattern in ignore_patterns:
            if pattern in path_str:
                return True
        return False

    def _hash_file(
        self, hasher: hashlib.sha256, file_path: Path, include_path: bool = False
    ):
        """Hash a single file"""
        try:
            # Include relative path in hash if requested
            if include_path:
                rel_path = file_path.relative_to(self.project_root)
                hasher.update(str(rel_path).encode())

            # Hash file contents
            with open(file_path, "rb") as f:
                while chunk := f.read(8192):
                    hasher.update(chunk)

        except Exception as e:
            logging.warning(f"Failed to hash file {file_path}: {e}")

    def get_python_files(self) -> List[Path]:
        """Get all Python files in the project"""
        py_files = list(self.project_root.rglob("*.py"))
        return [f for f in py_files if not self._should_ignore(f)]
