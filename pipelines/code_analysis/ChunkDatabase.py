import sqlite3
import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple


class ChunkDatabase:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    # ------------------------
    # Schema
    # ------------------------
    def _create_tables(self):
        cursor = self.conn.cursor()

        # Functions table - contains everything needed
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS functions (
                                                     id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                     fqn TEXT NOT NULL,  -- fully qualified name
                                                     project_id TEXT NOT NULL,
                                                     function_name TEXT NOT NULL,
                                                     module_name TEXT,
                                                     class_name TEXT,
                                                     source_code TEXT NOT NULL,
                                                     signature TEXT NOT NULL,
                                                     parameters TEXT,  -- JSON array
                                                     return_annotation TEXT,
                                                     decorators TEXT,  -- JSON array
                                                     docstring TEXT,
                                                     is_async BOOLEAN DEFAULT FALSE,
                                                     is_method BOOLEAN DEFAULT FALSE,
                                                     is_staticmethod BOOLEAN DEFAULT FALSE,
                                                     is_classmethod BOOLEAN DEFAULT FALSE,
                                                     is_property BOOLEAN DEFAULT FALSE,
                                                     parent_class_fqn TEXT,  -- if method, the class FQN
                                                     module_fqn TEXT NOT NULL,
                                                     file_path TEXT NOT NULL,
                                                     start_line INTEGER NOT NULL,
                                                     end_line INTEGER NOT NULL,
                                                     line_count INTEGER NOT NULL,
                                                     version INTEGER NOT NULL DEFAULT 0,
                                                     ast_hash TEXT NOT NULL,
                                                     called_functions TEXT,  -- JSON array
                                                     static_features TEXT,  -- JSON of StaticFeatures
                                                     is_slow BOOLEAN DEFAULT FALSE,
                                                     UNIQUE(fqn, project_id, version)
            )
            """
        )

        # Classes table - metadata only, references functions
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS classes (
                                                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                   fqn TEXT NOT NULL,
                                                   project_id TEXT NOT NULL,
                                                   class_name TEXT NOT NULL,
                                                   decorators TEXT,  -- JSON array
                                                   base_classes TEXT,  -- JSON array
                                                   docstring TEXT,
                                                   methods TEXT NOT NULL,  -- JSON array of method FQNs
                                                   class_variables TEXT,  -- JSON array
                                                   module_fqn TEXT NOT NULL,
                                                   file_path TEXT NOT NULL,
                                                   start_line INTEGER NOT NULL,
                                                   end_line INTEGER NOT NULL,
                                                   line_count INTEGER NOT NULL,
                                                   version INTEGER NOT NULL DEFAULT 0,
                                                   ast_hash TEXT NOT NULL,
                                                   UNIQUE(fqn, project_id, version)
            )
            """
        )

        # Modules table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS modules (
                                                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                   fqn TEXT NOT NULL,
                                                   project_id TEXT NOT NULL,
                                                   module_name TEXT NOT NULL,
                                                   source_code TEXT NOT NULL,  -- full module source
                                                   docstring TEXT,
                                                   imports TEXT,  -- JSON array
                                                   functions TEXT,  -- JSON array of function FQNs
                                                   classes TEXT,  -- JSON array of class FQNs
                                                   global_vars TEXT,  -- JSON array
                                                   file_path TEXT NOT NULL,
                                                   line_count INTEGER NOT NULL,
                                                   version INTEGER NOT NULL DEFAULT 0,
                                                   file_hash TEXT NOT NULL,
                                                   UNIQUE(fqn, project_id, version)
            )
            """
        )

        # Indexes for fast lookup
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_func_fqn ON functions(fqn, version)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_func_project ON functions(project_id, version)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_class_fqn ON classes(fqn, version)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_module_fqn ON modules(fqn, version)"
        )

        # Dynamic profiling normalized tables
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS dynamic_runs (
                                                        run_id TEXT PRIMARY KEY,
                                                        project_id TEXT NOT NULL,
                                                        timestamp TEXT NOT NULL,
                                                        total_time_ms REAL NOT NULL,
                                                        peak_memory_mb REAL DEFAULT 0
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS dynamic_functions (
                                                             id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                             project_id TEXT NOT NULL,
                                                             run_id TEXT NOT NULL,
                                                             fqn TEXT NOT NULL,
                                                             module_name TEXT NOT NULL,
                                                             function_name TEXT NOT NULL,
                                                             file_path TEXT NOT NULL,
                                                             inclusive_time_ms REAL,
                                                             exclusive_time_ms REAL,
                                                             call_count INTEGER,
                                                             avg_time_ms REAL,
                                                             fraction_of_total REAL,

                -- loop iteration stats
                                                             loop_iterations_total INTEGER DEFAULT 0,
                                                             loop_max_depth INTEGER DEFAULT 0,

                                                             UNIQUE(project_id, run_id, fqn)
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_dynfunc_run ON dynamic_functions(project_id, run_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_dynfunc_fqn ON dynamic_functions(fqn)"
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS dynamic_line_timings (
                                                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                                project_id TEXT NOT NULL,
                                                                run_id TEXT NOT NULL,
                                                                fqn TEXT NOT NULL,
                                                                file_path TEXT NOT NULL,
                                                                line_no INTEGER NOT NULL,
                                                                time_ms REAL NOT NULL,
                                                                hits INTEGER NOT NULL,
                                                                indentation_level INTEGER NOT NULL DEFAULT 0,
                                                                preview TEXT
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_dynline_run_fqn ON dynamic_line_timings(project_id, run_id, fqn)"
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS dynamic_edges (
                                                         id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                         project_id TEXT NOT NULL,
                                                         run_id TEXT NOT NULL,
                                                         caller TEXT NOT NULL,
                                                         callee TEXT NOT NULL,
                                                         time_ms REAL,
                                                         count INTEGER
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_dynedge_run ON dynamic_edges(project_id, run_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_dynedge_pair ON dynamic_edges(caller, callee)"
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS dynamic_hotspots (
                                                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                            project_id TEXT NOT NULL,
                                                            run_id TEXT NOT NULL,
                                                            rank INTEGER NOT NULL,
                                                            fqn TEXT NOT NULL,
                                                            exclusive_time_ms REAL NOT NULL,
                                                            fraction_of_total REAL NOT NULL,
                                                            call_count INTEGER NOT NULL,
                                                            avg_time_ms REAL NOT NULL,
                                                            UNIQUE(project_id, run_id, fqn)
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_dynhot_run ON dynamic_hotspots(project_id, run_id)"
        )


        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS embedding_predictions (
                                                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                   fqn TEXT NOT NULL,
                                                   project_id TEXT NOT NULL,
                                                   p_slow REAL NOT NULL,
                                                   is_slow BOOLEAN NOT NULL,
                                                   UNIQUE(fqn)
            )
            """
        )
        self.conn.commit()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_responses (
                                                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                    fqn TEXT NOT NULL,
                                                    project_id TEXT NOT NULL,
                                                    p_slow REAL NOT NULL,
                                                    is_slow BOOLEAN NOT NULL,
                                                    UNIQUE(fqn)
            )
            """
        )


        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_interactions (
                                                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

                -- Identity / grouping
                                                            session_id TEXT NOT NULL,         -- unique per optimize() call
                                                            project_id TEXT NOT NULL,
                                                            llm_model TEXT NOT NULL,
                                                            round INTEGER NOT NULL,           -- optimization round

                -- Context of the event
                                                            stage TEXT NOT NULL,              -- 'triage' | 'inspection' | 'repair' | 'post_reprofile'
                                                            event_type TEXT NOT NULL,         -- 'response' | 'code_request' | 'invalid_json' | 'invalid_fqn' | 'fix_submission' | 'fix_runtime_error' | 'status' | 'post_reprofile'
                                                            status TEXT,                      -- 'continue' | 'done' (when applicable)

                -- Payload (JSON)
                                                            code_requests_json TEXT,          -- JSON array
                                                            hypotheses_json TEXT,             -- JSON array (triage)
                                                            bottlenecks_json TEXT,            -- JSON array (inspection, includes replacement_source)
                                                            invalid_fqns_json TEXT,           -- JSON array of missing FQNs

                -- Raw model IO and errors
                                                            raw_model_output TEXT,            -- raw content from the model before parsing
                                                            parsed_json TEXT,                 -- final JSON string you parsed (for auditing)
                                                            error_type TEXT,                  -- e.g., 'invalid_json', 'runtime_error'
                                                            error_message TEXT,
                                                            stacktrace TEXT,

                -- Optional usage/cost
                                                            usage_prompt_tokens INTEGER,
                                                            usage_completion_tokens INTEGER,
                                                            usage_total_tokens INTEGER,

                -- Free-form ext metadata (latency, hashes, before/after timing, etc.)
                                                            meta_json TEXT
            )
            """
        )

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_llm_interactions_session ON llm_interactions(session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_llm_interactions_proj_round ON llm_interactions(project_id, round)")

        self.conn.commit()

    # ------------------------
    # Inserts for static code
    # ------------------------
    def insert_function_with_features(self, chunk: "FunctionChunk"):
        """Insert function with static features"""
        cursor = self.conn.cursor()

        features_json = None
        if chunk.static_features:
            features_json = json.dumps(asdict(chunk.static_features))

        cursor.execute(
            """
            INSERT OR REPLACE INTO functions (
                fqn, project_id, function_name, source_code, signature,
                parameters, return_annotation, decorators, docstring,
                is_async, is_method, is_staticmethod, is_classmethod, is_property,
                parent_class_fqn, module_fqn, file_path, start_line, end_line,
                line_count, version, ast_hash, called_functions, static_features, is_slow
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk.fqn,
                chunk.project_id,
                chunk.fqn.split(".")[-1],
                chunk.source_code,
                chunk.signature,
                json.dumps(chunk.parameters),
                chunk.return_annotation,
                json.dumps(chunk.decorators),
                chunk.docstring,
                chunk.is_async,
                chunk.is_method,
                chunk.is_staticmethod,
                chunk.is_classmethod,
                chunk.is_property,
                chunk.class_name,
                chunk.module_name,
                chunk.file_path,
                chunk.start_line,
                chunk.end_line,
                chunk.end_line - chunk.start_line + 1,
                chunk.version,
                chunk.ast_hash,
                json.dumps(chunk.called_functions),
                features_json,
                chunk.is_slow
            ),
        )
        self.conn.commit()

    def insert_class(self, chunk: "ClassChunk"):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO classes (
                fqn, project_id, class_name, decorators, base_classes,
                docstring, methods, class_variables, module_fqn, file_path,
                start_line, end_line, line_count, version, ast_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk.fqn,
                chunk.project_id,
                chunk.fqn.split(".")[-1],
                json.dumps(chunk.decorators),
                json.dumps(chunk.base_classes),
                chunk.docstring,
                json.dumps(chunk.methods),
                json.dumps(chunk.class_attributes),
                chunk.module_name,
                chunk.file_path,
                chunk.start_line,
                chunk.end_line,
                chunk.end_line - chunk.start_line + 1,
                chunk.version,
                chunk.ast_hash,
            ),
        )
        self.conn.commit()

    def insert_module(self, chunk: "ModuleChunk"):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO modules (
                fqn, project_id, module_name, source_code, docstring,
                imports, functions, classes, global_vars, file_path,
                line_count, version, file_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk.fqn,
                chunk.project_id,
                chunk.fqn,
                chunk.source_code,
                chunk.docstring,
                json.dumps(chunk.imports + chunk.from_imports),
                json.dumps(chunk.functions),
                json.dumps(chunk.classes),
                json.dumps(chunk.global_variables),
                chunk.file_path,
                chunk.end_line,
                chunk.version,
                chunk.ast_hash,
            ),
        )
        self.conn.commit()

    def insert_chunks(self, chunks: List["CodeChunk"]):
        for chunk in chunks:
            if chunk.chunk_type == "function":
                self.insert_function_with_features(chunk)
            elif chunk.chunk_type == "class":
                self.insert_class(chunk)
            elif chunk.chunk_type == "module":
                self.insert_module(chunk)

    # ------------------------
    # Inserts for dynamic profiling
    # ------------------------
    def insert_dynamic_run(
        self,
        project_id: str,
        run_id: str,
        total_time_ms: float,
        timestamp: str,
        peak_memory_mb: float = 0.0,
    ):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO dynamic_runs (run_id, project_id, timestamp, total_time_ms, peak_memory_mb)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                run_id,
                project_id,
                timestamp,
                float(total_time_ms),
                float(peak_memory_mb),
            ),
        )
        self.conn.commit()

    def insert_dynamic_function_metric(
        self,
        project_id: str,
        run_id: str,
        fqn: str,
        module_name: str,
        function_name: str,
        file_path: str,
        inclusive_time_ms: float,
        exclusive_time_ms: float,
        call_count: int,
        avg_time_ms: float,
        fraction_of_total: float,
    ):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO dynamic_functions (
                project_id, run_id, fqn, module_name, function_name, file_path,
                inclusive_time_ms, exclusive_time_ms, call_count, avg_time_ms, fraction_of_total
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                run_id,
                fqn,
                module_name,
                function_name,
                file_path,
                float(inclusive_time_ms or 0.0),
                float(exclusive_time_ms or 0.0),
                int(call_count or 0),
                float(avg_time_ms or 0.0),
                float(fraction_of_total or 0.0),
            ),
        )
        self.conn.commit()

    def bulk_insert_line_timings(
        self,
        project_id: str,
        run_id: str,
        fqn: str,
        file_path: str,
        timings: List[Dict[str, Any]],
    ):
        cursor = self.conn.cursor()
        rows = []
        for t in timings:
            rows.append(
                (
                    project_id,
                    run_id,
                    fqn,
                    file_path,
                    int(t.get("line", 0) or 0),
                    float(t.get("time_ms", 0.0) or 0.0),
                    int(t.get("hits", 0) or 0),
                    1 if t.get("is_loop_like") else 0,
                    t.get("preview", None),
                )
            )
        cursor.executemany(
            """
            INSERT INTO dynamic_line_timings (
                project_id, run_id, fqn, file_path, line_no, time_ms, hits, is_loop_like, preview
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self.conn.commit()

    def insert_dynamic_edge(self, project_id: str, run_id: str, edge: Dict):
        """Insert dynamic call graph edge"""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO dynamic_edges (
                project_id, run_id, caller, callee, time_ms, count
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                run_id,
                edge["caller"],
                edge["callee"],
                float(edge.get("time_ms", 0.0) or 0.0),
                int(edge.get("count", 0) or 0),
            ),
        )
        self.conn.commit()

    # ------------------------
    # Hotspots (post-analysis)
    # ------------------------
    def clear_dynamic_hotspots(self, project_id: str, run_id: str):
        cursor = self.conn.cursor()
        cursor.execute(
            "DELETE FROM dynamic_hotspots WHERE project_id = ? AND run_id = ?",
            (project_id, run_id),
        )
        self.conn.commit()

    def insert_dynamic_hotspots(
        self, project_id: str, run_id: str, hotspots: List[Dict[str, Any]]
    ):
        cursor = self.conn.cursor()
        rows = []
        for rank, h in enumerate(hotspots, start=1):
            rows.append(
                (
                    project_id,
                    run_id,
                    rank,
                    h["fqn"],
                    float(h["exclusive_time_ms"]),
                    float(h["fraction_of_total"]),
                    int(h["call_count"]),
                    float(h["avg_time_ms"]),
                )
            )
        cursor.executemany(
            """
            INSERT INTO dynamic_hotspots (
                project_id, run_id, rank, fqn, exclusive_time_ms, fraction_of_total, call_count, avg_time_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self.conn.commit()

    # ------------------------
    # Queries for pipeline/debug
    # ------------------------
    def get_top_hot_functions(
        self, project_id: str, run_id: str, n: int = 10
    ) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT fqn, exclusive_time_ms, fraction_of_total, call_count, avg_time_ms
            FROM dynamic_hotspots
            WHERE project_id = ? AND run_id = ?
            ORDER BY rank ASC
            LIMIT ?
            """,
            (project_id, run_id, n),
        )
        return [dict(r) for r in cursor.fetchall()]

    def fetch_dynamic_functions(
        self, project_id: str, run_id: str
    ) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM dynamic_functions
            WHERE project_id = ? AND run_id = ?
            """,
            (project_id, run_id),
        )
        return [dict(r) for r in cursor.fetchall()]

    # ------------------------
    # Other existing getters (unchanged)
    # ------------------------
    def get_function(
        self, fqn: str, project_id: str, version: Optional[int] = None
    ) -> Optional[Dict]:
        cursor = self.conn.cursor()
        if version is None:
            cursor.execute(
                """
                SELECT * FROM functions
                WHERE fqn = ? AND project_id = ?
                ORDER BY version DESC LIMIT 1
                """,
                (fqn, project_id),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM functions
                WHERE fqn = ? AND project_id = ? AND version = ?
                """,
                (fqn, project_id, version),
            )

        row = cursor.fetchone()
        if row:
            result = dict(row)
            result["parameters"] = (
                json.loads(result["parameters"]) if result["parameters"] else []
            )
            result["decorators"] = (
                json.loads(result["decorators"]) if result["decorators"] else []
            )
            result["called_functions"] = (
                json.loads(result["called_functions"])
                if result["called_functions"]
                else []
            )
            return result
        return None

    def get_functions(self, fqns: List[str], project_id: str) -> List[Dict]:
        results = []
        for fqn in fqns:
            func = self.get_function(fqn, project_id)
            if func:
                results.append(func)
        return results

    def get_class(
        self, fqn: str, project_id: str, version: Optional[int] = None
    ) -> Optional[Dict]:
        cursor = self.conn.cursor()
        if version is None:
            cursor.execute(
                """
                SELECT * FROM classes
                WHERE fqn = ? AND project_id = ?
                ORDER BY version DESC LIMIT 1
                """,
                (fqn, project_id),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM classes
                WHERE fqn = ? AND project_id = ? AND version = ?
                """,
                (fqn, project_id, version),
            )

        row = cursor.fetchone()
        if row:
            result = dict(row)
            result["methods"] = (
                json.loads(result["methods"]) if result["methods"] else []
            )
            result["decorators"] = (
                json.loads(result["decorators"]) if result["decorators"] else []
            )
            result["base_classes"] = (
                json.loads(result["base_classes"]) if result["base_classes"] else []
            )
            result["class_variables"] = (
                json.loads(result["class_variables"])
                if result["class_variables"]
                else []
            )
            return result
        return None

    def get_class_with_methods(self, fqn: str, project_id: str) -> Optional[Dict]:
        class_info = self.get_class(fqn, project_id)
        if not class_info:
            return None

        method_sources = []
        for method_fqn in class_info["methods"]:
            method = self.get_function(method_fqn, project_id)
            if method:
                method_sources.append(method)

        class_info["method_sources"] = method_sources
        return class_info

    def get_module(
        self, fqn: str, project_id: str, version: Optional[int] = None
    ) -> Optional[Dict]:
        cursor = self.conn.cursor()
        if version is None:
            cursor.execute(
                """
                SELECT * FROM modules
                WHERE fqn = ? AND project_id = ?
                ORDER BY version DESC LIMIT 1
                """,
                (fqn, project_id),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM modules
                WHERE fqn = ? AND project_id = ? AND version = ?
                """,
                (fqn, project_id, version),
            )

        row = cursor.fetchone()
        if row:
            result = dict(row)
            result["imports"] = (
                json.loads(result["imports"]) if result["imports"] else []
            )
            result["functions"] = (
                json.loads(result["functions"]) if result["functions"] else []
            )
            result["classes"] = (
                json.loads(result["classes"]) if result["classes"] else []
            )
            result["global_vars"] = (
                json.loads(result["global_vars"]) if result["global_vars"] else []
            )
            return result
        return None

    def update_function_version(
        self, fqn: str, project_id: str, new_source: str, new_version: int
    ):
        current = self.get_function(fqn, project_id)
        if not current:
            raise ValueError(f"Function {fqn} not found")

        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO functions (
                fqn, project_id, function_name, source_code, signature,
                parameters, return_annotation, decorators, docstring,
                is_async, is_method, is_staticmethod, is_classmethod, is_property,
                parent_class_fqn, module_fqn, file_path, start_line, end_line,
                line_count, version, ast_hash, called_functions
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fqn,
                project_id,
                current["function_name"],
                new_source,
                current["signature"],
                json.dumps(current["parameters"]),
                current["return_annotation"],
                json.dumps(current["decorators"]),
                current["docstring"],
                current["is_async"],
                current["is_method"],
                current["is_staticmethod"],
                current["is_classmethod"],
                current["is_property"],
                current["parent_class_fqn"],
                current["module_fqn"],
                current["file_path"],
                current["start_line"],
                current["end_line"],
                len(new_source.split("\n")),
                new_version,
                f"updated_{new_version}",
                json.dumps(current["called_functions"]),
            ),
        )
        self.conn.commit()

    def get_all_functions(
        self, project_id: str, latest_only: bool = True
    ) -> List[Dict]:
        cursor = self.conn.cursor()
        if latest_only:
            cursor.execute(
                """
                SELECT * FROM functions
                WHERE project_id = ? AND version = (
                    SELECT MAX(version) FROM functions f2
                    WHERE f2.fqn = functions.fqn AND f2.project_id = functions.project_id
                )
                """,
                (project_id,),
            )
        else:
            cursor.execute(
                "SELECT * FROM functions WHERE project_id = ?", (project_id,)
            )

        results = []
        for row in cursor.fetchall():
            result = dict(row)
            result["parameters"] = (
                json.loads(result["parameters"]) if result["parameters"] else []
            )
            result["decorators"] = (
                json.loads(result["decorators"]) if result["decorators"] else []
            )
            result["called_functions"] = (
                json.loads(result["called_functions"])
                if result["called_functions"]
                else []
            )
            results.append(result)
        return results

    def reconstruct_module(self, module_fqn: str, project_id: str) -> Optional[str]:
        module = self.get_module(module_fqn, project_id)
        if not module:
            return None
        return module["source_code"]

    def close(self):
        self.conn.close()

    def execute_sql(self, sql_string: str):
        """
        Generic SQL execution function.

        Returns:
        - None if no results
        - Single value if result is 1 row × 1 column
        - Dict if result is 1 row × multiple columns
        - List of dicts if result is multiple rows
        """
        cursor = self.conn.cursor()
        cursor.execute(sql_string)

        # Get column names
        columns = (
            [description[0] for description in cursor.description]
            if cursor.description
            else []
        )

        # Fetch all results
        rows = cursor.fetchall()

        # No results
        if not rows:
            return None

        # Single row, single column - return just the value
        if len(rows) == 1 and len(columns) == 1:
            return rows[0][0]

        # Single row, multiple columns - return dict
        if len(rows) == 1:
            return dict(zip(columns, rows[0]))

        # Multiple rows - return list of dicts
        return [dict(zip(columns, row)) for row in rows]

    def execute_write_sql(self, sql_string: str, params: tuple = None):
        """
        Execute INSERT, UPDATE, DELETE, or other write operations.

        Args:
            sql_string: SQL statement to execute
            params: Optional tuple of parameters for parameterized queries

        Returns:
            Dict with:
            - lastrowid: ID of last inserted row (useful for INSERT)
            - rowcount: Number of affected rows
        """
        cursor = self.conn.cursor()

        if params:
            cursor.execute(sql_string, params)
        else:
            cursor.execute(sql_string)

        self.conn.commit()

        return {
            'lastrowid': cursor.lastrowid,
            'rowcount': cursor.rowcount
        }

    def update_dynamic_function_extras(
        self, project_id: str, run_id: str, fqn: str, extras: Dict[str, Any]
    ):
        if not extras:
            return
        keys = []
        vals = []
        for k, v in extras.items():
            keys.append(f"{k} = ?")
            vals.append(v)
        vals.extend([project_id, run_id, fqn])
        sql = f"""
            UPDATE dynamic_functions
            SET {", ".join(keys)}
            WHERE project_id = ? AND run_id = ? AND fqn = ?
        """
        cursor = self.conn.cursor()
        cursor.execute(sql, tuple(vals))
        self.conn.commit()

    def get_functions_by_file_map(
        self, project_id: str
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Get a mapping of file paths to functions with normalized paths"""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT fqn, file_path, start_line, end_line
            FROM functions
            WHERE project_id = ? AND version = (
                SELECT MAX(version) FROM functions f2
                WHERE f2.fqn = functions.fqn AND f2.project_id = functions.project_id
            )
            """,
            (project_id,),
        )

        mapping: Dict[str, List[Dict[str, Any]]] = {}

        for r in cursor.fetchall():
            d = dict(r)
            original_path = d["file_path"]

            # Try multiple path normalizations to increase matching chances
            paths_to_try = []

            # 1. Resolved absolute path
            try:
                resolved_path = str(Path(original_path).resolve())
                paths_to_try.append(resolved_path)
            except Exception:
                pass

            # 2. Original path as stored
            paths_to_try.append(original_path)

            # 3. Absolute path without resolution (preserves symlinks)
            try:
                abs_path = str(Path(original_path).absolute())
                if abs_path not in paths_to_try:
                    paths_to_try.append(abs_path)
            except Exception:
                pass

            # Add to mapping under all possible paths
            for path in paths_to_try:
                if path:
                    mapping.setdefault(path, []).append(
                        {
                            "fqn": d["fqn"],
                            "file_path": path,
                            "start_line": d["start_line"],
                            "end_line": d["end_line"],
                        }
                    )

        # Sort intervals per file for faster lookup
        for fp in mapping:
            mapping[fp].sort(key=lambda x: (x["start_line"], x["end_line"]))

        # Log for debugging
        import logging

        logging.debug(
            f"File map created with {len(mapping)} unique paths for {project_id}"
        )
        if mapping and logging.getLogger().isEnabledFor(logging.DEBUG):
            sample_paths = list(mapping.keys())[:3]
            logging.debug(f"Sample paths in map: {sample_paths}")

        return mapping

    def get_loop_line_aggregates(
        self, project_id: str, run_id: str
    ) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT
                fqn,
                SUM(CASE WHEN is_loop_like = 1 THEN hits ELSE 0 END) AS total_hits,
                SUM(CASE WHEN is_loop_like = 1 THEN time_ms ELSE 0 END) AS total_time_ms,
                SUM(CASE WHEN is_loop_like = 1 THEN 1 ELSE 0 END) AS loop_lines
            FROM dynamic_line_timings
            WHERE project_id = ? AND run_id = ?
            GROUP BY fqn
            """,
            (project_id, run_id),
        )
        return [dict(r) for r in cursor.fetchall()]

    def get_loop_iteration_aggregates(
        self, project_id: str, run_id: str
    ) -> List[Dict[str, Any]]:
        """Get loop iteration counts and max depth per function"""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT
                fqn,
                SUM(hits) AS total_hits,
                MAX(indentation_level) AS max_depth,
                COUNT(*) AS total_lines
            FROM dynamic_line_timings
            WHERE project_id = ? AND run_id = ? AND indentation_level > 0
            GROUP BY fqn
            """,
            (project_id, run_id),
        )
        return [dict(r) for r in cursor.fetchall()]

    def bulk_insert_line_timings(
        self,
        project_id: str,
        run_id: str,
        fqn: str,
        file_path: str,
        timings: List[Dict[str, Any]],
    ):
        cursor = self.conn.cursor()
        rows = []
        for t in timings:
            rows.append(
                (
                    project_id,
                    run_id,
                    fqn,
                    file_path,
                    int(t.get("line", 0) or 0),
                    float(t.get("time_ms", 0.0) or 0.0),
                    int(t.get("hits", 0) or 0),
                    int(t.get("indentation_level", 0) or 0),
                    t.get("preview", None),
                )
            )
        cursor.executemany(
            """
            INSERT INTO dynamic_line_timings (
                project_id, run_id, fqn, file_path, line_no, time_ms, hits, indentation_level, preview
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self.conn.commit()
