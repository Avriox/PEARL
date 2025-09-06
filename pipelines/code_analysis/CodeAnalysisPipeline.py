import os
from pathlib import Path
import logging
from typing import List

from .DynamicProfiler import DynamicProfiler
from .Project import Project
from .CodeAnalyzer import CodeAnalyzer
from .ChunkDatabase import ChunkDatabase
from .HotspotAnalyzer import HotspotAnalyzer


class CodeAnalysisPipeline:
    def __init__(self, db_path: Path = Path("chunks.db")):
        logging.info("=== Initialized CodeAnalysisPipeline ===")
        self.projects: List[Project] = []

        logging.info("Deleting old database file if present")
        try:
            Path(db_path).unlink(missing_ok=True)
        except Exception as e:
            logging.warning(f"Could not delete database file {db_path}: {e}")

        self.db = ChunkDatabase(db_path)

        self.call_graphs = {}

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

    def extract_and_analyze(self):
        """Extract code chunks and perform static analysis in one pass"""
        logging.info("=== Extracting and analyzing code ===")

        for project in self.projects:
            project_id = project.project_info.get("id", "unknown")
            project_name = project.project_info.get("name", "Unknown")

            logging.info(f"Analyzing project: {project_name}")

            # Single-pass analysis
            analyzer = CodeAnalyzer(project_id, project.directory)
            chunks, call_graph = analyzer.analyze_project()

            logging.info(f"Extracted {len(chunks)} chunks")

            # Store chunks with static features
            for chunk in chunks:
                if getattr(chunk, "chunk_type", None) == "function":
                    self.db.insert_function_with_features(chunk)
                else:
                    self.db.insert_chunks([chunk])

            # Save call graph
            artifacts_dir = Path(f"artifacts/{project_id}")
            analyzer.save_call_graph(artifacts_dir)
            self.call_graphs[project_id] = call_graph

            logging.info(
                f"Call graph: {call_graph.number_of_nodes()} nodes, "
                f"{call_graph.number_of_edges()} edges"
            )

    def run_dynamic_analysis(self):
        logging.info("=== Running dynamic analysis ===")
        hotspot_analyzer = HotspotAnalyzer(self.db)

        for project in self.projects:
            project_id = project.project_info.get("id", "unknown")
            project_name = project.project_info.get("name", "Unknown")

            logging.info(f"Dynamically analyzing project: {project_name}")
            profiler = DynamicProfiler(project, self.db)

            # Profile (writes to DB)
            run = profiler.profile_function_timing(args=None, warmup_runs=2)

            print(
                f"\nProfiling run: {run.run_id} | total_time_ms={run.total_time_ms:.2f}"
            )

            # Post-profiling hotspot analysis (writes hotspots to DB)
            hotspot_analyzer.compute_hotspots(project_id, run.run_id, top_n=50)

            # Print top functions from DB
            print("\nTop hot functions (exclusive time):")
            top = self.db.get_top_hot_functions(project_id, run.run_id, n=10)
            for row in top:
                print(
                    f"  {row['fqn']}: {row['exclusive_time_ms']:.2f}ms "
                    f"({row['fraction_of_total']:.1%}, "
                    f"calls={row['call_count']}, avg={row['avg_time_ms']:.3f}ms)"
                )

    def close(self):
        """Clean up resources"""
        self.db.close()
