import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import psutil
import textwrap


@dataclass
class FunctionMetrics:
    """Metrics for a single function"""

    fqn: str
    inclusive_time_ms: float
    exclusive_time_ms: float
    call_count: int
    avg_time_ms: float
    fraction_of_total: float
    file_path: str = ""
    module_name: str = ""
    function_name: str = ""

    # Extended metrics (populated by separate passes later if needed)
    line_hotspots: List[Dict] = field(default_factory=list)
    memory_alloc_bytes: float = 0.0
    peak_memory_bytes: float = 0.0


@dataclass
class ProfilingRun:
    """Results from a single profiling run"""

    run_id: str
    project_id: str
    timestamp: str
    total_time_ms: float

    function_metrics: Dict[str, FunctionMetrics] = field(default_factory=dict)


class DynamicProfiler:
    """Profiles Python projects and writes raw data to DB:
    - dynamic_runs
    - dynamic_functions
    - dynamic_line_timings (for loop tracking)
    - dynamic_edges (dynamic call graph)
    """

    PYI_START = "<<<PEARL_PYINSTRUMENT_JSON_START>>>"
    PYI_END = "<<<PEARL_PYINSTRUMENT_JSON_END>>>"
    CPROF_START = "<<<PEARL_CPROFILE_JSON_START>>>"
    CPROF_END = "<<<PEARL_CPROFILE_JSON_END>>>"
    LINE_START = "<<<PEARL_LINEPROF_JSON_START>>>"
    LINE_END = "<<<PEARL_LINEPROF_JSON_END>>>"
    MEM_START = "<<<PEARL_MEMORY_JSON_START>>>"
    MEM_END = "<<<PEARL_MEMORY_JSON_END>>>"

    def __init__(self, project: "Project", db: "ChunkDatabase"):
        self.project = project
        self.db = db
        self.project_id = project.project_info.get("id", "unknown")
        self.last_run: Optional[ProfilingRun] = None

        if hasattr(psutil, "Process"):
            try:
                p = psutil.Process()
                if hasattr(p, "cpu_affinity"):
                    p.cpu_affinity([0, 1])
                    logging.info("CPU affinity set to cores 0,1 for controller process")
            except Exception:
                pass

    def profile_function_timing(
        self,
        args: Optional[List[str]] = None,
        warmup_runs: int = 2,
        top_k_for_lines: int = 10,
    ) -> ProfilingRun:
        """Profile (function-level with cProfile + structure with pyinstrument) and store into DB."""
        logging.info(f"Starting function timing profiling for {self.project_id}")

        # Warmup runs
        for i in range(warmup_runs):
            logging.info(f"Warmup run {i+1}/{warmup_runs}")
            self.project.run(args)

        info = self.project.build_entrypoint_info(args=args)

        # 1) pyinstrument: for structure + dynamic edges
        pyi_code = self._build_pyinstrument_wrapper_code(
            entry_type=info["type"],
            target=info["target"],
            argv0=info["argv0"],
            args=info["args"],
        )
        pyi_res = self.project.run_with_profiling(pyi_code)
        if pyi_res.returncode != 0:
            logging.error("pyinstrument wrapper failed")
            logging.error(f"stdout:\n{pyi_res.stdout}")
            logging.error(f"stderr:\n{pyi_res.stderr}")
            raise RuntimeError("pyinstrument profiling failed")

        pyi_json_str = self._extract_json_block(
            pyi_res.stdout, self.PYI_START, self.PYI_END
        )
        if not pyi_json_str:
            logging.error("Failed to parse pyinstrument JSON output")
            logging.error(f"stdout:\n{pyi_res.stdout}")
            raise RuntimeError("Could not find pyinstrument JSON markers in output")
        pyi_payload = json.loads(pyi_json_str)
        session_json = pyi_payload.get("session", {})
        pyi_total_ms = float(pyi_payload.get("total_time_sec", 0.0)) * 1000.0

        func_metrics_from_pyi, edges = self._aggregate_pyinstrument(session_json)

        # 2) cProfile: accurate per-function call counts and times
        cp_code = self._build_cprofile_wrapper_code(
            entry_type=info["type"],
            target=info["target"],
            argv0=info["argv0"],
            args=info["args"],
        )
        cp_res = self.project.run_with_profiling(cp_code)
        if cp_res.returncode != 0:
            logging.error("cProfile wrapper failed")
            logging.error(f"stdout:\n{cp_res.stdout}")
            logging.error(f"stderr:\n{cp_res.stderr}")
            raise RuntimeError("cProfile profiling failed")

        cp_json_str = self._extract_json_block(
            cp_res.stdout, self.CPROF_START, self.CPROF_END
        )
        if not cp_json_str:
            logging.error("Failed to parse cProfile JSON output")
            logging.error(f"stdout:\n{cp_res.stdout}")
            raise RuntimeError("Could not find cProfile JSON markers in output")

        cp_payload = json.loads(cp_json_str)
        cp_total_ms = float(cp_payload.get("total_time_sec", 0.0)) * 1000.0

        # Merge cProfile numbers into metrics
        func_metrics = self._apply_cprofile_to_metrics(
            func_metrics_from_pyi, cp_payload
        )

        total_time_ms = (
            cp_total_ms
            if cp_total_ms > 0
            else (pyi_total_ms if pyi_total_ms > 0 else 0.0)
        )

        # Normalize fractions and avg
        for fm in func_metrics.values():
            fm.fraction_of_total = (
                (fm.exclusive_time_ms / total_time_ms) if total_time_ms > 0 else 0.0
            )
            fm.avg_time_ms = fm.exclusive_time_ms / max(1, fm.call_count)

        # 3) Simple peak memory tracking
        mem_code = self._build_memory_wrapper_code(
            entry_type=info["type"],
            target=info["target"],
            argv0=info["argv0"],
            args=info["args"],
        )
        mem_res = self.project.run_with_profiling(mem_code)
        peak_memory_mb = 0.0
        if mem_res.returncode == 0:
            mem_json_str = self._extract_json_block(
                mem_res.stdout, self.MEM_START, self.MEM_END
            )
            if mem_json_str:
                mem_payload = json.loads(mem_json_str)
                peak_memory_mb = float(mem_payload.get("peak_memory_mb", 0.0))
                logging.info(f"Peak memory usage: {peak_memory_mb:.2f}MB")
            else:
                logging.warning("Failed to parse memory JSON output")
        else:
            logging.warning("Memory profiling failed")

        # Persist run and functions
        run_id = f"{self.project_id}-{int(time.time())}"
        run = ProfilingRun(
            run_id=run_id,
            project_id=self.project_id,
            timestamp=datetime.utcnow().isoformat(),
            total_time_ms=total_time_ms,
            function_metrics=func_metrics,
        )
        self.db.insert_dynamic_run(
            project_id=self.project_id,
            run_id=run_id,
            total_time_ms=total_time_ms,
            timestamp=run.timestamp,
            peak_memory_mb=peak_memory_mb,
        )

        for fqn, fm in func_metrics.items():
            self.db.insert_dynamic_function_metric(
                project_id=self.project_id,
                run_id=run_id,
                fqn=fqn,
                module_name=fm.module_name,
                function_name=fm.function_name,
                file_path=fm.file_path,
                inclusive_time_ms=fm.inclusive_time_ms,
                exclusive_time_ms=fm.exclusive_time_ms,
                call_count=fm.call_count,
                avg_time_ms=fm.avg_time_ms,
                fraction_of_total=fm.fraction_of_total,
            )

        # Persist dynamic edges
        for (caller, callee), data in edges.items():
            self.db.insert_dynamic_edge(
                project_id=self.project_id,
                run_id=run_id,
                edge={
                    "caller": caller,
                    "callee": callee,
                    "time_ms": data.get("time_ms", 0.0),
                    "count": data.get("count", 0),
                },
            )

        # 4) Line profile for loop tracking - profile ALL functions that were executed
        all_targets = []
        for fqn, fm in func_metrics.items():
            if fm.call_count > 0:  # Only profile functions that were actually called
                module, func = self._split_module_func_simple(fqn)
                if module and func and self._valid_identifier_chain(func):
                    all_targets.append({"module": module, "func": func})

        # Line profile in batches to avoid command line too long
        batch_size = 20
        logging.info(
            f"Line profiling {len(all_targets)} functions in batches of {batch_size}"
        )

        for i in range(0, len(all_targets), batch_size):
            batch = all_targets[i : i + batch_size]
            logging.debug(
                f"Line profiling batch {i//batch_size + 1}: {len(batch)} functions"
            )

            lp_code = self._build_line_profiler_wrapper_code(
                entry_type=info["type"],
                target=info["target"],
                argv0=info["argv0"],
                args=info["args"],
                targets=batch,
            )
            lp_res = self.project.run_with_profiling(lp_code)

            if lp_res.returncode == 0:
                lp_json_str = self._extract_json_block(
                    lp_res.stdout, self.LINE_START, self.LINE_END
                )
                if lp_json_str:
                    lp_payload = json.loads(lp_json_str)
                    self._persist_line_timings(run_id, lp_payload)
                else:
                    logging.warning(
                        f"Failed to parse line_profiler JSON for batch {i//batch_size + 1}"
                    )
            else:
                logging.warning(f"line_profiler failed for batch {i//batch_size + 1}")

        # After all line profiling is done, calculate loop stats
        self._apply_loop_stats_to_db(run_id)

        self.last_run = run
        return run

    # --------------------
    # Helpers
    # --------------------
    def _extract_json_block(
        self, text: str, start_marker: str, end_marker: str
    ) -> Optional[str]:
        if not text:
            return None
        start = text.find(start_marker)
        if start == -1:
            return None
        start += len(start_marker)
        end = text.find(end_marker, start)
        if end == -1:
            return None
        return text[start:end].strip()

    def _is_project_file(self, file_path: Optional[str]) -> bool:
        if not file_path:
            return False
        try:
            proj_dir = str(self.project.directory.resolve())
            fp = str(Path(file_path).resolve())
            # Exclude venv and site-packages even if inside project dir
            if self.project.venv_path:
                venv_dir = str(Path(self.project.venv_path).resolve())
                if fp.startswith(venv_dir):
                    return False
            if "site-packages" in fp or "/dist-packages/" in fp:
                return False
            return fp.startswith(proj_dir)
        except Exception:
            return False

    def _file_to_module(self, file_path: str) -> str:
        """Best-effort: map a file path to module name relative to project root."""
        try:
            proj_dir = self.project.directory.resolve()
            p = Path(file_path).resolve()
            rel = p.relative_to(proj_dir)
            parts = list(rel.parts)
            if parts[-1] == "__init__.py":
                parts = parts[:-1]
            else:
                parts[-1] = parts[-1].rsplit(".", 1)[0]
            return ".".join(parts)
        except Exception:
            return Path(file_path).stem

    def _frame_to_fqn(self, frame: Dict[str, Any]) -> Optional[Tuple[str, str, str]]:
        """Return (fqn, module_name, function_name) for a frame if it's project code."""
        file_path = (
            frame.get("file_path") or frame.get("filename") or frame.get("file") or ""
        )
        func_name = (
            frame.get("function")
            or frame.get("func_name")
            or frame.get("name")
            or "<unknown>"
        )
        if not self._is_project_file(file_path):
            return None
        module = self._file_to_module(file_path)
        fqn = f"{module}.{func_name}"
        return fqn, module, func_name

    def _aggregate_pyinstrument(
        self, session_json: Dict[str, Any]
    ) -> Tuple[Dict[str, FunctionMetrics], Dict[Tuple[str, str], Dict[str, float]]]:
        """Traverse pyinstrument JSON. Return (function_metrics, edges)."""
        root = session_json.get("root_frame") or session_json.get("rootFrame") or {}
        metrics: Dict[str, FunctionMetrics] = {}
        edges: Dict[Tuple[str, str], Dict[str, float]] = {}

        def traverse(frame: Dict[str, Any]) -> float:
            if not frame:
                return 0.0
            time_sec = float(frame.get("time", 0.0) or 0.0)

            # Process children first
            child_times = []
            for ch in frame.get("children", []):
                child_times.append((ch, traverse(ch)))
            total_children_sec = sum(t for _, t in child_times)

            # Record function metrics for project frames
            fqn_triplet = self._frame_to_fqn(frame)
            if fqn_triplet:
                fqn, module, func_name = fqn_triplet
                file_path = (
                    frame.get("file_path")
                    or frame.get("filename")
                    or frame.get("file")
                    or ""
                )
                excl_ms = max(0.0, (time_sec - total_children_sec) * 1000.0)
                incl_ms = max(0.0, time_sec * 1000.0)
                if fqn not in metrics:
                    metrics[fqn] = FunctionMetrics(
                        fqn=fqn,
                        inclusive_time_ms=0.0,
                        exclusive_time_ms=0.0,
                        call_count=0,
                        avg_time_ms=0.0,
                        fraction_of_total=0.0,
                        file_path=str(file_path),
                        module_name=module,
                        function_name=func_name,
                    )
                m = metrics[fqn]
                m.inclusive_time_ms += incl_ms
                m.exclusive_time_ms += excl_ms
                m.call_count += 1  # frame instances

                # Record edges to child project frames
                for ch_frame, ch_time_sec in child_times:
                    ch_triplet = self._frame_to_fqn(ch_frame)
                    if ch_triplet:
                        ch_fqn, _, _ = ch_triplet
                        key = (fqn, ch_fqn)
                        if key not in edges:
                            edges[key] = {"time_ms": 0.0, "count": 0}
                        edges[key]["time_ms"] += ch_time_sec * 1000.0
                        edges[key]["count"] += 1

            return time_sec

        traverse(root)
        return metrics, edges

    def _apply_cprofile_to_metrics(
        self, func_metrics: Dict[str, FunctionMetrics], cp_payload: Dict[str, Any]
    ) -> Dict[str, FunctionMetrics]:
        """Merge cProfile stats (accurate ncalls/times) into FunctionMetrics, project files only."""
        for rec in cp_payload.get("functions", []):
            file_path = rec.get("file", "")
            if not self._is_project_file(file_path):
                continue
            func_name = rec.get("function", "")
            module = self._file_to_module(file_path)
            fqn = f"{module}.{func_name}"

            excl_ms = float(rec.get("tottime", 0.0)) * 1000.0
            incl_ms = float(rec.get("cumtime", 0.0)) * 1000.0
            try:
                ncalls = int(rec.get("ncalls", 0) or 0)
            except Exception:
                ncalls = 0

            if fqn not in func_metrics:
                func_metrics[fqn] = FunctionMetrics(
                    fqn=fqn,
                    inclusive_time_ms=incl_ms,
                    exclusive_time_ms=excl_ms,
                    call_count=ncalls,
                    avg_time_ms=(excl_ms / max(1, ncalls)),
                    fraction_of_total=0.0,
                    file_path=str(file_path),
                    module_name=module,
                    function_name=func_name,
                )
            else:
                m = func_metrics[fqn]
                # Prefer cProfile's accurate numbers
                m.inclusive_time_ms = incl_ms
                m.exclusive_time_ms = excl_ms
                m.call_count = ncalls
                m.avg_time_ms = excl_ms / max(1, ncalls)

        return func_metrics

    def _valid_identifier_chain(self, name: str) -> bool:
        try:
            return all(part.isidentifier() for part in name.split(".") if part)
        except Exception:
            return False

    def _split_module_func_simple(self, fqn: str) -> (Optional[str], Optional[str]):
        if not fqn or "." not in fqn:
            return None, None
        parts = fqn.split(".")
        func = parts[-1]
        module = ".".join(parts[:-1])
        return module, func

    # --------------------
    # Wrapper builders
    # --------------------
    def _build_pyinstrument_wrapper_code(
                self, entry_type: str, target: str, argv0: str, args: List[str]
        ) -> str:
        project_dir = str(self.project.directory.resolve())

        code = f"""
        import sys, runpy, time, json
        from pyinstrument import Profiler
        try:
            from pyinstrument.renderers.jsonrenderer import JSONRenderer
        except Exception:
            from pyinstrument.renderers import JSONRenderer

        # Add project directory to path for local modules
        PROJECT_DIR = {repr(project_dir)}
        if PROJECT_DIR not in sys.path:
            sys.path.insert(0, PROJECT_DIR)

        ENTRY_TYPE = {repr(entry_type)}
        ENTRY_TARGET = {repr(target)}
        ENTRY_ARGS = {repr(list(args or []))}
        ARGV0 = {repr(argv0)}
        START = {repr(self.PYI_START)}
        END = {repr(self.PYI_END)}

        sys.argv = [ARGV0] + list(ENTRY_ARGS)

        prof = Profiler()
        t0 = time.perf_counter()
        prof.start()
        try:
            if ENTRY_TYPE == "script":
                runpy.run_path(ENTRY_TARGET, run_name="__main__")
            else:
                runpy.run_module(ENTRY_TARGET, run_name="__main__")
        finally:
            prof.stop()
            t1 = time.perf_counter()

        renderer = JSONRenderer()
        payload = {{"session": json.loads(renderer.render(prof.last_session)), "total_time_sec": (t1 - t0)}}
        print(START, flush=True)
        print(json.dumps(payload), flush=True)
        print(END, flush=True)
        """
        return textwrap.dedent(code)

    def _build_cprofile_wrapper_code(
            self, entry_type: str, target: str, argv0: str, args: List[str]
    ) -> str:
        project_dir = str(self.project.directory.resolve())

        code = f"""
        import sys, runpy, time, json, cProfile, pstats
        
        # Add project directory to path for local modules
        PROJECT_DIR = {repr(project_dir)}
        if PROJECT_DIR not in sys.path:
            sys.path.insert(0, PROJECT_DIR)
        
        ENTRY_TYPE = {repr(entry_type)}
        ENTRY_TARGET = {repr(target)}
        ENTRY_ARGS = {repr(list(args or []))}
        ARGV0 = {repr(argv0)}
        START = {repr(self.CPROF_START)}
        END = {repr(self.CPROF_END)}

        sys.argv = [ARGV0] + list(ENTRY_ARGS)

        pr = cProfile.Profile()
        t0 = time.perf_counter()
        pr.enable()
        try:
            if ENTRY_TYPE == "script":
                runpy.run_path(ENTRY_TARGET, run_name="__main__")
            else:
                runpy.run_module(ENTRY_TARGET, run_name="__main__")
        finally:
            pr.disable()
            t1 = time.perf_counter()

        stats = pstats.Stats(pr)
        out = []
        for (filename, lineno, funcname), stat in stats.stats.items():
            cc, nc, tt, ct, callers = stat
            try:
                ncalls = int(nc) if not isinstance(nc, str) else int(str(nc).split("/")[0])
            except Exception:
                ncalls = 0
            out.append({{
                "file": filename,
                "line_no": int(lineno),
                "function": funcname,
                "ncalls": ncalls,
                "tottime": float(tt),
                "cumtime": float(ct)
            }})

        payload = {{"functions": out, "total_time_sec": (t1 - t0)}}
        print(START, flush=True)
        print(json.dumps(payload), flush=True)
        print(END, flush=True)
        """
        return textwrap.dedent(code)

    def _build_memory_wrapper_code(
            self, entry_type: str, target: str, argv0: str, args: List[str]
    ) -> str:
        project_dir = str(self.project.directory.resolve())

        code = f"""
        import sys, runpy, time, json, tracemalloc, gc
        
        # Add project directory to path for local modules
        PROJECT_DIR = {repr(project_dir)}
        if PROJECT_DIR not in sys.path:
            sys.path.insert(0, PROJECT_DIR)
        
        ENTRY_TYPE = {repr(entry_type)}
        ENTRY_TARGET = {repr(target)}
        ENTRY_ARGS = {repr(list(args or []))}
        ARGV0 = {repr(argv0)}
        START = {repr(self.MEM_START)}
        END = {repr(self.MEM_END)}

        sys.argv = [ARGV0] + list(ENTRY_ARGS)

        # Force garbage collection before starting
        gc.collect()

        # Start tracemalloc
        tracemalloc.start()

        t0 = time.perf_counter()
        try:
            if ENTRY_TYPE == "script":
                runpy.run_path(ENTRY_TARGET, run_name="__main__")
            else:
                runpy.run_module(ENTRY_TARGET, run_name="__main__")
        finally:
            t1 = time.perf_counter()

            # Get peak memory
            current, peak = tracemalloc.get_traced_memory()
            peak_mb = peak / (1024 * 1024)

            # Stop tracemalloc
            tracemalloc.stop()

            payload = {{
                "peak_memory_mb": peak_mb,
                "total_time_sec": (t1 - t0)
            }}

            print(START, flush=True)
            print(json.dumps(payload), flush=True)
            print(END, flush=True)
        """
        return textwrap.dedent(code)

    def _build_line_profiler_wrapper_code(
            self,
            entry_type: str,
            target: str,
            argv0: str,
            args: List[str],
            targets: List[Dict[str, str]],
    ) -> str:
        targets_payload = [{"module": t["module"], "func": t["func"]} for t in targets]
        project_dir = str(self.project.directory.resolve())

        code = f"""
    import sys, runpy, time, json, importlib, inspect, ast
    from line_profiler import LineProfiler

    ENTRY_TYPE = {repr(entry_type)}
    ENTRY_TARGET = {repr(target)}
    ENTRY_ARGS = {repr(list(args or []))}
    ARGV0 = {repr(argv0)}
    TARGET_FUNCS = {json.dumps(targets_payload)}
    PROJECT_DIR = {repr(project_dir)}
    START = {repr(self.LINE_START)}
    END = {repr(self.LINE_END)}

    # Add project directory to Python path so modules can be imported
    if PROJECT_DIR not in sys.path:
        sys.path.insert(0, PROJECT_DIR)

    sys.argv = [ARGV0] + list(ENTRY_ARGS)

    lp = LineProfiler()
    debug_info = []

    # Map various key formats to function info
    func_info_map = {{}}

    def detect_loop_lines(file_path):
        \"\"\"Detect which lines contain loop constructs\"\"\"
        loop_header_lines = set()  # Only the for/while lines themselves
        loop_body_lines = {{}}  # line -> loop_depth (for context)

        try:
            with open(file_path, 'r') as f:
                source = f.read()
                lines = source.split('\\n')

            # Parse AST to find loop constructs
            tree = ast.parse(source)

            class LoopVisitor(ast.NodeVisitor):
                def __init__(self):
                    self.loop_stack = []  # Track nesting depth

                def visit_For(self, node):
                    # For loops - mark the header line
                    loop_header_lines.add(node.lineno)
                    self.loop_stack.append(node.lineno)

                    # Mark all lines in the loop body with depth (for context only)
                    for stmt in ast.walk(node):
                        if hasattr(stmt, 'lineno'):
                            loop_body_lines[stmt.lineno] = len(self.loop_stack)

                    self.generic_visit(node)
                    self.loop_stack.pop()

                def visit_While(self, node):
                    # While loops - mark the header line
                    loop_header_lines.add(node.lineno)
                    self.loop_stack.append(node.lineno)

                    # Mark all lines in the loop body with depth (for context only)
                    for stmt in ast.walk(node):
                        if hasattr(stmt, 'lineno'):
                            loop_body_lines[stmt.lineno] = len(self.loop_stack)

                    self.generic_visit(node)
                    self.loop_stack.pop()

                def visit_ListComp(self, node):
                    # List comprehensions - the whole line is the loop
                    loop_header_lines.add(node.lineno)
                    loop_body_lines[node.lineno] = len(self.loop_stack) + 1
                    self.generic_visit(node)

                def visit_DictComp(self, node):
                    # Dict comprehensions
                    loop_header_lines.add(node.lineno)
                    loop_body_lines[node.lineno] = len(self.loop_stack) + 1
                    self.generic_visit(node)

                def visit_SetComp(self, node):
                    # Set comprehensions
                    loop_header_lines.add(node.lineno)
                    loop_body_lines[node.lineno] = len(self.loop_stack) + 1
                    self.generic_visit(node)

            visitor = LoopVisitor()
            visitor.visit(tree)

            # Also detect with regex for edge cases AST might miss
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if (stripped.startswith('for ') or 
                    stripped.startswith('while ') or
                    (' for ' in line and any(bracket in line for bracket in ['[', '(', '{{']))):
                    loop_header_lines.add(i)

            return loop_header_lines, loop_body_lines

        except Exception as e:
            debug_info.append(f"Error detecting loops in {{file_path}}: {{e}}")
            return set(), {{}}

    def add_target(module_name, func_chain):
        try:
            debug_info.append(f"Attempting to import module: {{module_name}}")
            mod = importlib.import_module(module_name)
            debug_info.append(f"Successfully imported {{module_name}}")

            obj = mod
            for attr in func_chain.split("."):
                debug_info.append(f"Getting attribute: {{attr}}")
                obj = getattr(obj, attr)

            if inspect.isfunction(obj) or inspect.ismethod(obj):
                # Get the actual function object
                func_obj = obj if inspect.isfunction(obj) else obj.__func__

                # Add to line profiler
                lp.add_function(func_obj)

                # Get function info
                try:
                    file_path = inspect.getfile(func_obj)
                    func_name = func_obj.__name__
                    first_line = func_obj.__code__.co_firstlineno

                    # Create the key that LineProfiler will use
                    lp_key = (file_path, first_line, func_name)

                    # Detect loops in this file
                    loop_header_lines, loop_body_lines = detect_loop_lines(file_path)

                    # Store mapping
                    func_info_map[lp_key] = {{
                        'file_path': file_path,
                        'func_name': func_name,
                        'module_name': module_name,
                        'func_chain': func_chain,
                        'first_line': first_line,
                        'loop_header_lines': loop_header_lines,
                        'loop_body_lines': loop_body_lines
                    }}

                    debug_info.append(f"Added function {{module_name}}.{{func_chain}} ({{func_name}}) from {{file_path}} line {{first_line}}")
                    debug_info.append(f"  Detected {{len(loop_header_lines)}} loop header lines: {{sorted(list(loop_header_lines))[:5]}}")
                    return True, module_name, func_chain
                except Exception as e:
                    debug_info.append(f"Could not get file for {{module_name}}.{{func_chain}}: {{e}}")
                    return False, module_name, func_chain

            debug_info.append(f"Failed to add {{module_name}}.{{func_chain}} - not function/method (type: {{type(obj)}})")
            return False, module_name, func_chain
        except Exception as e:
            debug_info.append(f"Exception adding {{module_name}}.{{func_chain}}: {{e}}")
            return False, module_name, func_chain

    added = []
    for spec in TARGET_FUNCS:
        ok, m, f = add_target(spec["module"], spec["func"])
        if ok:
            added.append({{"module": m, "func": f}})

    debug_info.append(f"Successfully added {{len(added)}} functions to line profiler")

    t0 = time.perf_counter()
    globs = dict(runpy=runpy, ENTRY_TYPE=ENTRY_TYPE, ENTRY_TARGET=ENTRY_TARGET)
    code_str = "runpy.run_path(ENTRY_TARGET, run_name='__main__')" if ENTRY_TYPE == "script" else "runpy.run_module(ENTRY_TARGET, run_name='__main__')"
    lp.runctx(code_str, globs, {{}})
    t1 = time.perf_counter()

    stats = lp.get_stats()
    unit = getattr(stats, "unit", 1.0) or 1.0
    out_funcs = []

    debug_info.append(f"LineProfiler found {{len(stats.timings)}} functions with timing data")

    # Build a file cache for reading source lines
    file_cache = {{}}

    def get_src_line(fp, n):
        if fp in file_cache:
            lines_local = file_cache[fp]
        else:
            try:
                with open(fp, "r") as fh:
                    lines_local = fh.readlines()
            except Exception as e:
                debug_info.append(f"Could not read file {{fp}}: {{e}}")
                lines_local = []
            file_cache[fp] = lines_local
        if 1 <= n <= len(lines_local):
            return lines_local[n-1].rstrip()
        return ""

    for key, timings in stats.timings.items():
        if isinstance(key, tuple) and len(key) == 3:
            file_path, first_line, func_name = key

            # Get additional info from our mapping
            info = func_info_map.get(key, {{}})
            loop_header_lines = info.get('loop_header_lines', set())
            loop_body_lines = info.get('loop_body_lines', {{}})

        else:
            debug_info.append(f"Unexpected key format: {{key}}")
            file_path = "<unknown>"
            func_name = "<unknown>"
            loop_header_lines = set()
            loop_body_lines = {{}}

        debug_info.append(f"Processing function '{{func_name}}' from '{{file_path}}' with {{len(timings)}} lines")
        debug_info.append(f"  Loop header lines detected: {{sorted(list(loop_header_lines))}}")

        lines = []
        loop_iterations = 0
        max_loop_depth = 0
        header_hits = []

        for lineno, nhits, t in timings:
            time_ms = float(t) * float(unit) * 1000.0
            src_line = get_src_line(file_path, lineno)

            # Check if this line is a loop header (for/while statement)
            is_loop_header = lineno in loop_header_lines
            # Check if this line is anywhere in a loop body (for depth calculation)
            loop_depth = loop_body_lines.get(lineno, 0)

            if is_loop_header:
                # Only count hits on actual loop headers
                loop_iterations += nhits
                max_loop_depth = max(max_loop_depth, loop_depth)
                header_hits.append((lineno, nhits, src_line[:50]))

            lines.append({{
                "line": int(lineno), 
                "time_ms": time_ms, 
                "hits": int(nhits), 
                "indentation_level": 0,
                "preview": src_line[:100],
                "is_loop_header": is_loop_header,
                "loop_depth": loop_depth
            }})

        debug_info.append(f"  {{func_name}}: {{loop_iterations}} loop iterations, max loop depth: {{max_loop_depth}}")

        # Log loop header hits for verification
        if header_hits:
            debug_info.append(f"  Loop header hits:")
            for lineno, nhits, preview in header_hits:
                debug_info.append(f"    Line {{lineno}}: {{nhits}} hits, '{{preview}}'")
        else:
            debug_info.append(f"  No loop headers detected for this function")

        if lines:
            lines.sort(key=lambda x: x["time_ms"], reverse=True)
            out_funcs.append({{
                "file_path": file_path,
                "function": func_name,
                "timings": lines,
                "loop_iterations": loop_iterations,
                "max_loop_depth": max_loop_depth
            }})

    payload = {{
        "functions": out_funcs, 
        "profiled_functions": added, 
        "total_time_sec": (t1 - t0),
        "debug_info": debug_info
    }}
    print(START, flush=True)
    print(json.dumps(payload), flush=True)
    print(END, flush=True)
    """
        return textwrap.dedent(code)

    def _persist_line_timings(self, run_id: str, lp_payload: Dict[str, Any]) -> None:
        """Persist line timings for each profiled function."""

        # Log debug info if present
        debug_info = lp_payload.get("debug_info", [])
        if debug_info:
            logging.info("Line profiler debug info:")
            for msg in debug_info:
                logging.info(f"  {msg}")

        funcs = lp_payload.get("functions", [])
        for f in funcs:
            file_path = f.get("file_path", "")
            func_name = f.get("function", "")
            module = self._file_to_module(file_path)
            fqn = f"{module}.{func_name}"
            timings = f.get("timings", [])

            # Get loop stats directly from the line profiler results
            loop_iterations = f.get("loop_iterations", 0)
            max_loop_depth = f.get("max_loop_depth", 0)

            # Store loop stats immediately
            if loop_iterations > 0 or max_loop_depth > 0:
                self.db.update_dynamic_function_extras(
                    self.project_id,
                    run_id,
                    fqn,
                    extras={
                        "loop_iterations_total": loop_iterations,
                        "loop_max_depth": max_loop_depth,
                    },
                )
                logging.debug(
                    f"Updated loop stats for {fqn}: {loop_iterations} iterations, depth {max_loop_depth}"
                )

            # Store line timings (optional, for detailed analysis)
            if timings:
                self.db.bulk_insert_line_timings(
                    project_id=self.project_id,
                    run_id=run_id,
                    fqn=fqn,
                    file_path=file_path,
                    timings=timings,
                )

    def _apply_loop_stats_to_db(self, run_id: str) -> None:
        """Calculate and store loop iteration statistics from line profiler data"""
        # This method is now mostly handled by _persist_line_timings
        # But we can add a summary log here

        # Get final loop stats from database
        cursor = self.db.conn.cursor()
        cursor.execute(
            """
            SELECT fqn, loop_iterations_total, loop_max_depth
            FROM dynamic_functions
            WHERE project_id = ? AND run_id = ? AND loop_iterations_total > 0
            """,
            (self.project_id, run_id),
        )

        results = cursor.fetchall()
        functions_with_loops = len(results)
        total_iterations_all = sum(row[1] for row in results)

        logging.info(
            f"Final loop stats: {functions_with_loops} functions with loops, {total_iterations_all} total iterations"
        )

        if results:
            logging.info("Functions with loops:")
            for fqn, iterations, depth in results:
                logging.info(f"  {fqn}: {iterations} iterations, max depth {depth}")

    def detect_loop_lines(file_path):
        """Detect which lines contain loop constructs"""
        loop_header_lines = set()  # Only the for/while lines themselves
        loop_body_lines = {}  # line -> loop_depth (for context)

        try:
            with open(file_path, "r") as f:
                source = f.read()
                lines = source.split("\n")

            # Parse AST to find loop constructs
            tree = ast.parse(source)

            class LoopVisitor(ast.NodeVisitor):
                def __init__(self):
                    self.loop_stack = []  # Track nesting depth

                def visit_For(self, node):
                    # For loops - mark the header line
                    loop_header_lines.add(node.lineno)
                    self.loop_stack.append(node.lineno)

                    # Mark all lines in the loop body with depth (for context only)
                    for stmt in ast.walk(node):
                        if hasattr(stmt, "lineno"):
                            loop_body_lines[stmt.lineno] = len(self.loop_stack)

                    self.generic_visit(node)
                    self.loop_stack.pop()

                def visit_While(self, node):
                    # While loops - mark the header line
                    loop_header_lines.add(node.lineno)
                    self.loop_stack.append(node.lineno)

                    # Mark all lines in the loop body with depth (for context only)
                    for stmt in ast.walk(node):
                        if hasattr(stmt, "lineno"):
                            loop_body_lines[stmt.lineno] = len(self.loop_stack)

                    self.generic_visit(node)
                    self.loop_stack.pop()

                def visit_ListComp(self, node):
                    # List comprehensions - the whole line is the loop
                    loop_header_lines.add(node.lineno)
                    loop_body_lines[node.lineno] = len(self.loop_stack) + 1
                    self.generic_visit(node)

                def visit_DictComp(self, node):
                    # Dict comprehensions
                    loop_header_lines.add(node.lineno)
                    loop_body_lines[node.lineno] = len(self.loop_stack) + 1
                    self.generic_visit(node)

                def visit_SetComp(self, node):
                    # Set comprehensions
                    loop_header_lines.add(node.lineno)
                    loop_body_lines[node.lineno] = len(self.loop_stack) + 1
                    self.generic_visit(node)

            visitor = LoopVisitor()
            visitor.visit(tree)

            # Also detect with regex for edge cases AST might miss
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if (
                    stripped.startswith("for ")
                    or stripped.startswith("while ")
                    or (
                        " for " in line
                        and any(bracket in line for bracket in ["[", "(", "{"])
                    )
                ):
                    loop_header_lines.add(i)

            return loop_header_lines, loop_body_lines

        except Exception as e:
            debug_info.append(f"Error detecting loops in {file_path}: {e}")
            return set(), {}
