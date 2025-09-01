# Updated CodeAnalysisPipeline.py
from pathlib import Path
import logging
from typing import List, Optional

from .Project import Project
from .CodeParser import CodeParser
from .ChunkDatabase import ChunkDatabase
from .ProjectHasher import ProjectHasher


class CodeAnalysisPipeline:
    def __init__(self, db_path: Path = Path("chunks.db")):
        logging.info("=== Initialized CodeAnalysisPipeline ===")
        self.projects: List[Project] = []
        self.db = ChunkDatabase(db_path)

    def load_projects(self, path):
        logging.info(f"Loading projects from {path}")
        directories = [item for item in Path(path).iterdir() if item.is_dir()]
        logging.info(f"Found {len(directories)} directories")

        for directory in directories:
            try:
                project = Project(directory)
                self.projects.append(project)
                logging.info(f"Loaded project: {project.project_info.get('name')}")
            except Exception as e:
                logging.error(f"Failed to load project from {directory}: {e}")

    def extract_code_chunks(self, force_reparse: bool = False):
        """Extract and store code chunks from all loaded projects"""
        logging.info("=== Extracting code chunks from projects ===")

        total_projects = len(self.projects)
        parsed_projects = 0
        skipped_projects = 0

        for idx, project in enumerate(self.projects, 1):
            project_id = project.project_info.get("id", "unknown")
            project_name = project.project_info.get("name", "Unknown")

            logging.info(
                f"\n[{idx}/{total_projects}] Checking project: {project_name} ({project_id})"
            )

            # Compute hash for THIS SPECIFIC PROJECT
            hasher = ProjectHasher(project.directory)
            current_hash = hasher.compute_project_hash()
            logging.info(f"  Current hash: {current_hash[:16]}...")

            # Check if THIS SPECIFIC PROJECT needs parsing
            stored_hash = self.db.get_project_hash(project_id)

            # Determine if we need to parse THIS PROJECT
            needs_parsing = False
            reason = ""

            if force_reparse:
                needs_parsing = True
                reason = "force_reparse=True"
            elif not stored_hash:
                needs_parsing = True
                reason = "not in database"
            elif stored_hash != current_hash:
                needs_parsing = True
                reason = f"hash changed (was {stored_hash[:16]}...)"

            if not needs_parsing:
                # THIS PROJECT hasn't changed, skip it
                skipped_projects += 1
                chunks_count = len(self.db.get_chunks_by_project(project_id))
                logging.info(f"  ✓ Skipping (unchanged, {chunks_count} chunks in DB)")
                continue

            # THIS PROJECT needs parsing
            parsed_projects += 1
            logging.info(f"  → Parsing project (reason: {reason})")

            # If project exists but changed, clear its old data
            if stored_hash and stored_hash != current_hash:
                logging.info(f"  → Clearing old data for project")
                self.db.clear_project_data(project_id)

            # Parse THIS SPECIFIC PROJECT
            parser = CodeParser(project_id, project.directory)

            # Parse project returns a tuple now: (chunks, parsed_files)
            chunks, parsed_files = parser.parse_project()

            logging.info(
                f"  → Extracted {len(chunks)} chunks from {len(parsed_files)} files"
            )

            # Store chunks for THIS PROJECT
            self.db.insert_chunks(chunks)

            # Store file information and structure
            for parsed_file in parsed_files:
                # Store file info
                self.db.insert_file_info(parsed_file.file_info, project_id)

                # Store file elements
                for element in parsed_file.file_elements:
                    self.db.insert_file_element(
                        element, parsed_file.file_info, project_id
                    )

                # Store code segments
                for segment in parsed_file.code_segments:
                    self.db.insert_code_segment(
                        segment, parsed_file.file_info, project_id
                    )

            # Update THIS PROJECT's metadata
            python_files = hasher.get_python_files()
            self.db.update_project(
                project_id=project_id,
                project_name=project_name,
                project_hash=current_hash,
                file_count=len(python_files),
                chunk_count=len(chunks),
            )

            # Log statistics for THIS PROJECT
            functions = [c for c in chunks if c.chunk_type == "function"]
            classes = [c for c in chunks if c.chunk_type == "class"]
            modules = [c for c in chunks if c.chunk_type == "module"]

            logging.info(
                f"  → Breakdown: {len(functions)} functions, {len(classes)} classes, {len(modules)} modules"
            )
            logging.info(f"  → Hash saved: {current_hash[:16]}...")

        # Summary
        logging.info(f"\n=== Summary ===")
        logging.info(f"Total projects: {total_projects}")
        logging.info(f"Parsed: {parsed_projects}")
        logging.info(f"Skipped (unchanged): {skipped_projects}")

    def extract_single_project(self, project_id: str, force: bool = False):
        """Extract chunks for a single project by ID"""
        project = next(
            (p for p in self.projects if p.project_info.get("id") == project_id), None
        )

        if not project:
            logging.error(f"Project {project_id} not loaded")
            return

        project_name = project.project_info.get("name", "Unknown")
        logging.info(f"Processing single project: {project_name} ({project_id})")

        # Compute hash for this project
        hasher = ProjectHasher(project.directory)
        current_hash = hasher.compute_project_hash()

        # Check if we need to parse
        stored_hash = self.db.get_project_hash(project_id)

        if not force and stored_hash == current_hash:
            chunks_count = len(self.db.get_chunks_by_project(project_id))
            logging.info(
                f"Project unchanged (hash match), {chunks_count} chunks already in DB"
            )
            return

        # Clear old data if exists
        if stored_hash:
            logging.info(f"Clearing old data for project")
            self.db.clear_project_data(project_id)

        # Parse the project
        parser = CodeParser(project_id, project.directory)
        chunks, parsed_files = parser.parse_project()

        logging.info(f"Extracted {len(chunks)} chunks from {len(parsed_files)} files")

        # Store in database
        self.db.insert_chunks(chunks)

        # Store file information
        for parsed_file in parsed_files:
            self.db.insert_file_info(parsed_file.file_info, project_id)

            for element in parsed_file.file_elements:
                self.db.insert_file_element(element, parsed_file.file_info, project_id)

            for segment in parsed_file.code_segments:
                self.db.insert_code_segment(segment, parsed_file.file_info, project_id)

        # Update metadata
        python_files = hasher.get_python_files()
        self.db.update_project(
            project_id=project_id,
            project_name=project_name,
            project_hash=current_hash,
            file_count=len(python_files),
            chunk_count=len(chunks),
        )

        logging.info(f"Project {project_name} successfully parsed and stored")

    def get_project_chunks(self, project_id: str, chunk_type: Optional[str] = None):
        """Get all chunks for a specific project"""
        return self.db.get_chunks_by_project(project_id, chunk_type)

    def search_functions(self, query: str, project_id: Optional[str] = None):
        """Search for functions by name"""
        results = self.db.search_chunks(query, project_id)
        return [r for r in results if r["chunk_type"] == "function"]

    def get_function_code(self, fqn: str, project_id: str, version: int = 0):
        """Get the source code for a specific function"""
        chunk = self.db.get_chunk_by_fqn(fqn, project_id, version)
        if chunk:
            return chunk["source_code"]
        return None

    def get_project_status(self):
        """Get status of all loaded projects"""
        status = []
        for project in self.projects:
            project_id = project.project_info.get("id", "unknown")
            project_name = project.project_info.get("name", "Unknown")

            # Check if in database
            stored_hash = self.db.get_project_hash(project_id)

            # Compute current hash
            hasher = ProjectHasher(project.directory)
            current_hash = hasher.compute_project_hash()

            chunks_count = (
                len(self.db.get_chunks_by_project(project_id)) if stored_hash else 0
            )

            status.append(
                {
                    "project_id": project_id,
                    "project_name": project_name,
                    "in_database": stored_hash is not None,
                    "up_to_date": stored_hash == current_hash,
                    "needs_parsing": stored_hash != current_hash,
                    "chunks_count": chunks_count,
                    "current_hash": current_hash[:16] + "...",
                    "stored_hash": stored_hash[:16] + "..." if stored_hash else None,
                }
            )

        return status

    def close(self):
        """Clean up resources"""
        self.db.close()
