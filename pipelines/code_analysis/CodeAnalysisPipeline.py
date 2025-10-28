import ast
import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path
import logging
from typing import List, Dict, Any

import astor

from .DynamicProfiler import DynamicProfiler
from .Project import Project
from .CodeAnalyzer import CodeAnalyzer
from .ChunkDatabase import ChunkDatabase
from .HotspotAnalyzer import HotspotAnalyzer

from pathlib import Path
from collections import defaultdict


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
            if directory != Path("test-projects/python-chess-master"):
                continue

            # exclude : textdistance mccabe slugify sumy sortedcontainers
            # if directory in [
            #     Path("test-projects/textdistance-master"),
            #     Path("test-projects/mccabe-master"),
            #     Path("test-projects/python-slugify-master"),
            #     Path("test-projects/sumy-main"),
            #     Path("test-projects/python-sortedcontainers-master"),
            # ]:
            #     continue
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

            run_config = project.config.get("run", {})
            args = run_config.get("default_args") if run_config else None
            # Profile (writes to DB)
            run = profiler.profile_function_timing(
                args=args, warmup_runs=5, profiled_runs=20
            )

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

    def get_projects(self):
        return self.projects

    def rerun_dynamic_analysis_for_project(self, project: "Project", bottlenecks: List[Dict[str, Any]], session_id: str = None, llm_model: str = None, round_idx: int = 0, embedding_pipe=None):
        """
        - For each bottleneck with replacement_source: insert a new version row with recomputed static features.
        - Build patch specs (with file_path+start_line) so dynamic profilers attribute time correctly.
        - Re-run dynamic profiling with patches; then hotspots.
        - If an EmbeddingPipeline is provided, re-score the project immediately so embedding_predictions reflect the patched code.
        """
        logging.info(f"=== Re-running dynamic analysis for {project.project_info.get('name')} with patches ===")
        project_id = project.project_info.get("id", "unknown")

        patches = []
        for b in bottlenecks or []:
            fqn = b.get("fqn")
            src = (b.get("replacement_source") or "").strip()
            if not fqn or not src.startswith("def "):
                continue

            prev = self.db.execute_sql(f"""
                SELECT *
                FROM functions
                WHERE project_id = '{project_id}' AND fqn = '{fqn}'
                ORDER BY version DESC
                LIMIT 1
            """)
            if not prev:
                logging.warning(f"Cannot patch {fqn}: not found in DB for project {project_id}")
                continue

            # Recompute static features for the new function source
            try:
                mod_ast = ast.parse(src)
                node = next((n for n in ast.walk(mod_ast) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))), None)
            except Exception as e:
                logging.error(f"Invalid replacement_source for {fqn}: {e}")
                continue
            if node is None:
                logging.error(f"No function def found in replacement_source for {fqn}")
                continue

            analyzer = CodeAnalyzer(project_id, project.directory)
            features = analyzer._analyze_function_ast(
                node=node,
                source_code=src,
                module_fqn=prev["module_name"],
                class_name=prev["class_name"],
            )
            static_features_json = json.dumps(asdict(features))

            is_async = isinstance(node, ast.AsyncFunctionDef)
            decorators_list = [astor.to_source(d).strip() for d in getattr(node, "decorator_list", [])]
            docstring = ast.get_docstring(node)
            parameters = [arg.arg for arg in getattr(node, "args", ast.arguments(args=[], posonlyargs=[], kwonlyargs=[], vararg=None, kwarg=None)).args]
            return_annotation = astor.to_source(node.returns).strip() if getattr(node, "returns", None) else None

            signature = f"{node.name}({', '.join(parameters)})"
            if return_annotation:
                signature += f" -> {return_annotation}"

            # Called functions: use features.calls_made we just computed
            called_functions_json = json.dumps(features.calls_made)

            # Hash of AST (same approach as CodeAnalyzer._compute_ast_hash)
            try:
                dump = ast.dump(node, annotate_fields=False, include_attributes=False)
            except Exception:
                dump = src
            ast_hash = hashlib.sha256(dump.encode()).hexdigest()[:16]
            line_count = src.count("\n") + 1
            new_version = int(prev.get("version", 0)) + 1

            # Insert new versioned row (no file edits)
            # TODO is_slow should not be taken from prev but should be assumed to be 0 now.
            self.db.execute_write_sql("""
                                      INSERT INTO functions (
                                          fqn, project_id, function_name, module_name, class_name, source_code, signature,
                                          parameters, return_annotation, decorators, docstring, is_async, is_method,
                                          is_staticmethod, is_classmethod, is_property, parent_class_fqn, module_fqn,
                                          file_path, start_line, end_line, line_count, version, ast_hash, called_functions,
                                          static_features, is_slow
                                      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                      """, (
                                          prev["fqn"], prev["project_id"], prev["function_name"], prev["module_name"], prev["class_name"],
                                          src, signature, json.dumps(parameters), return_annotation, json.dumps(decorators_list),
                                          docstring, 1 if is_async else 0, prev["is_method"], prev["is_staticmethod"], prev["is_classmethod"],
                                          prev["is_property"], prev["parent_class_fqn"], prev["module_fqn"], prev["file_path"],
                                          prev["start_line"], prev["end_line"], line_count, new_version, ast_hash,
                                          called_functions_json, static_features_json, prev["is_slow"]
                                      ))

            # Build patch spec. IMPORTANT: pass ABSOLUTE file path + start_line for correct attribution
            abs_file = str((Path(project.directory) / prev["file_path"]).resolve())
            patches.append({
                "fqn": fqn,
                "src": src,
                "is_method": bool(prev["is_method"]),
                "is_staticmethod": bool(prev["is_staticmethod"]),
                "is_classmethod": bool(prev["is_classmethod"]),
                "is_property": bool(prev["is_property"]),
                "file_path": abs_file,
                "start_line": int(prev["start_line"] or 1),
            })

        if not patches:
            logging.info("No valid patches to apply; skipping patched run.")
            return None

        profiler = DynamicProfiler(project, self.db)
        hotspot_analyzer = HotspotAnalyzer(self.db)
        try:
            run = profiler.profile_function_timing(
                args=project.config.get("run", {}).get("default_args"),
                warmup_runs=5,              # keep warmups, now using patched code
                profiled_runs=10,           # keep your baseline multi-run default
                top_k_for_lines=10,
                patches=patches
            )
        except Exception as e:
            logging.error(f"Patched run failed: {e}")
            # Optionally log to llm_interactions if you track fix errors.
            if session_id and llm_model:
                self.db.execute_write_sql("""
                                          INSERT INTO llm_interactions (
                                              session_id, project_id, llm_model, round, stage, event_type, error_type, error_message, meta_json
                                          ) VALUES (?, ?, ?, ?, 'repair', 'fix_runtime_error', 'runtime_error', ?, ?)
                                          """, (session_id, project_id, llm_model, int(round_idx or 0), str(e), json.dumps({"fqns":[p["fqn"] for p in patches]})))
            return None

        hotspot_analyzer.compute_hotspots(project_id, run.run_id, top_n=50)

        # Immediately re-score the project so embedding_predictions reflect the patched code
        try:
            if embedding_pipe is not None:
                embedding_pipe.score_project(project)
            else:
                logging.info("No embedding pipeline provided; skipping re-scoring after patched run.")
        except Exception as e:
            logging.warning(f"Re-scoring failed after patched run for {project_id}: {e}")

        return run