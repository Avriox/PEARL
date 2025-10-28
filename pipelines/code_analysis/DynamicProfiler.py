import ast
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import psutil
import textwrap

from pipelines.code_analysis.CodeAnalyzer import FQNResolver


@dataclass
class FunctionMetrics:
    fqn: str
    inclusive_time_ms: float
    exclusive_time_ms: float
    call_count: int
    avg_time_ms: float
    fraction_of_total: float
    file_path: str = ""
    module_name: str = ""
    function_name: str = ""
    first_lineno: int = 0  # <-- add this

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
    PATCH_ERR_MARK = "<<<PEARL_PATCH_ERROR>>>"

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
            args=None,
            warmup_runs=2,
            profiled_runs=10,
            top_k_for_lines=10,
            patches: Optional[List[Dict[str, Any]]] = None
    ) -> ProfilingRun:
        logging.info(f"Starting function timing profiling for {self.project_id}")

        info = self.project.build_entrypoint_info(args=args)
        patches_json = json.dumps(patches or [])

        # 0) Apply patches once in a minimal, fast wrapper (no entrypoint run)
        if patches:
            patch_code = self._build_patch_only_wrapper_code(patches_json)
            res = self.project.run_with_profiling(patch_code)
            if res.returncode != 0:
                errs = self._extract_patch_errors((res.stdout or "") + "\n" + (res.stderr or ""))
                if errs:
                    raise RuntimeError(f"Patch apply failed: {json.dumps(errs)}")
                logging.error("Patch-only wrapper failed: stdout[:800]=%r stderr[:800]=%r",
                              (res.stdout or "")[:800], (res.stderr or "")[:800])
                raise RuntimeError("Patch apply failed (no diagnostics)")

        # 1) Warmup WITHOUT any wrapper (fast path, same as original behavior)
        for i in range(warmup_runs):
            logging.info(f"Warmup run {i+1}/{warmup_runs}")
            self.project.run(args)

        # Preload static recursion flags to decide whether to keep self-edges
        static_has_recursion: Dict[str, bool] = {}
        try:
            rows = self.db.execute_sql(
                f"""
                SELECT fqn, static_features
                FROM functions
                WHERE project_id = '{self.project_id}'
                """
            )
            for r in rows or []:
                sf = r.get("static_features")
                if not sf:
                    continue
                try:
                    sf_obj = json.loads(sf)
                    static_has_recursion[r["fqn"]] = bool(sf_obj.get("has_recursion", False))
                except Exception:
                    pass
        except Exception:
            pass

        def _is_synthetic(name: str) -> bool:
            try:
                return name.startswith("<") and name.endswith(">")
            except Exception:
                return False

        # Storage for multiple runs
        all_func_metrics: List[Dict[str, FunctionMetrics]] = []
        all_edges: List[Dict[Tuple[str, str], Dict[str, Any]]] = []
        all_total_times: List[float] = []
        all_peak_memories: List[float] = []
        all_line_profiles: List[Dict[str, Any]] = []

        # Run multiple profiled runs
        for run_num in range(profiled_runs):
            logging.info(f"Profiled run {run_num+1}/{profiled_runs}")

            # 1) pyinstrument (structure + edges)
            pyi_code = self._build_pyinstrument_wrapper_code(
                entry_type=info["type"],
                target=info["target"],
                argv0=info["argv0"],
                args=info["args"],
                patches_json=patches_json
            )
            pyi_res = self.project.run_with_profiling(pyi_code)
            if pyi_res.returncode != 0:
                errs = self._extract_patch_errors((pyi_res.stdout or "") + "\n" + (pyi_res.stderr or ""))
                if errs:
                    raise RuntimeError(f"Patch apply failed: {json.dumps(errs)}")
                logging.error("Pyinstrument wrapper failed: stdout[:800]=%r stderr[:800]=%r",
                              (pyi_res.stdout or "")[:800], (pyi_res.stderr or "")[:800])
                logging.warning(f"Pyinstrument failed on run {run_num+1}")
                continue

            pyi_json_str = self._extract_json_block(pyi_res.stdout, self.PYI_START, self.PYI_END)
            pyi_payload = json.loads(pyi_json_str)
            session_json = pyi_payload.get("session", {})
            pyi_total_ms = float(pyi_payload.get("total_time_sec", 0.0)) * 1000.0
            func_metrics_from_pyi, edges = self._aggregate_pyinstrument(session_json)

            # 2) cProfile (accurate timings)
            cp_code = self._build_cprofile_wrapper_code(
                entry_type=info["type"],
                target=info["target"],
                argv0=info["argv0"],
                args=info["args"],
                patches_json=patches_json
            )
            cp_res = self.project.run_with_profiling(cp_code)
            if cp_res.returncode != 0:
                errs = self._extract_patch_errors((cp_res.stdout or "") + "\n" + (cp_res.stderr or ""))
                if errs:
                    raise RuntimeError(f"Patch apply failed: {json.dumps(errs)}")
                logging.error("cProfile wrapper failed: stdout[:800]=%r stderr[:800]=%r",
                              (cp_res.stdout or "")[:800], (cp_res.stderr or "")[:800])
                logging.warning(f"cProfile failed on run {run_num+1}")
                continue

            cp_json_str = self._extract_json_block(cp_res.stdout, self.CPROF_START, self.CPROF_END)
            cp_payload = json.loads(cp_json_str)
            cp_total_ms = float(cp_payload.get("total_time_sec", 0.0)) * 1000.0

            # Merge cProfile
            func_metrics = self._apply_cprofile_to_metrics(func_metrics_from_pyi, cp_payload)

            total_time_ms = cp_total_ms if cp_total_ms > 0 else (pyi_total_ms if pyi_total_ms > 0 else 0.0)
            all_total_times.append(total_time_ms)

            # Resolve to fully qualified FQNs
            resolver = FQNResolver(self.db, self.project_id, self.project.directory)

            # a) Resolve function metrics
            resolved_func_metrics: Dict[str, FunctionMetrics] = {}
            temp_to_resolved = {}
            for temp_key, fm in func_metrics.items():
                resolved_fqn = resolver.resolve(
                    file_path=fm.file_path,
                    lineno=int(fm.first_lineno or 0),
                    fallback_module=fm.module_name,
                    funcname=fm.function_name,
                )
                temp_to_resolved[temp_key] = resolved_fqn

                if resolved_fqn not in resolved_func_metrics:
                    fm.fqn = resolved_fqn
                    fm.module_name = ".".join(resolved_fqn.split(".")[:-1])
                    fm.function_name = resolved_fqn.split(".")[-1]
                    resolved_func_metrics[resolved_fqn] = fm
                else:
                    acc = resolved_func_metrics[resolved_fqn]
                    acc.inclusive_time_ms += fm.inclusive_time_ms
                    acc.exclusive_time_ms += fm.exclusive_time_ms
                    acc.call_count += fm.call_count

            # Normalize (per run)
            for fm in resolved_func_metrics.values():
                fm.fraction_of_total = ((fm.exclusive_time_ms / total_time_ms) if total_time_ms > 0 else 0.0)
                fm.avg_time_ms = fm.exclusive_time_ms / max(1, fm.call_count)

            all_func_metrics.append(resolved_func_metrics)

            # b) Resolve edges
            resolved_edges: Dict[Tuple[str, str], Dict[str, Any]] = {}
            for (caller_temp, callee_temp), data in edges.items():
                cf = data.get("caller_file")
                cl = int(data.get("caller_line", 0) or 0)
                tf = data.get("callee_file")
                tl = int(data.get("callee_line", 0) or 0)

                caller_module_guess = (resolver.module_from_rel(resolver.rel_to_project(cf)) if cf else "")
                callee_module_guess = (resolver.module_from_rel(resolver.rel_to_project(tf)) if tf else "")

                caller_raw = caller_temp.split("@L")[0].split(".")[-1]
                callee_raw = callee_temp.split("@L")[0].split(".")[-1]

                caller_resolved = resolver.resolve(cf, cl, caller_module_guess, caller_raw)
                callee_resolved = resolver.resolve(tf, tl, callee_module_guess, callee_raw)

                if caller_resolved == callee_resolved:
                    if _is_synthetic(caller_raw) or _is_synthetic(callee_raw):
                        continue
                    if not static_has_recursion.get(caller_resolved, False):
                        continue

                key = (caller_resolved, callee_resolved)
                e = resolved_edges.setdefault(key, {"time_ms": 0.0, "count": 0})
                e["time_ms"] += float(data.get("time_ms", 0.0) or 0.0)
                e["count"] += int(data.get("count", 0) or 0)

            all_edges.append(resolved_edges)

            # 3) Memory profiling
            mem_code = self._build_memory_wrapper_code(
                entry_type=info["type"],
                target=info["target"],
                argv0=info["argv0"],
                args=info["args"],
                patches_json=patches_json
            )
            mem_res = self.project.run_with_profiling(mem_code)
            peak_memory_mb = 0.0
            if mem_res.returncode != 0:
                errs = self._extract_patch_errors((mem_res.stdout or "") + "\n" + (mem_res.stderr or ""))
                if errs:
                    raise RuntimeError(f"Patch apply failed: {json.dumps(errs)}")
                logging.error("Memory wrapper failed: stdout[:800]=%r stderr[:800]=%r",
                              (mem_res.stdout or "")[:800], (mem_res.stderr or "")[:800])
            else:
                mem_json_str = self._extract_json_block(mem_res.stdout, self.MEM_START, self.MEM_END)
                if mem_json_str:
                    mem_payload = json.loads(mem_json_str)
                    peak_memory_mb = float(mem_payload.get("peak_memory_mb", 0.0))
            all_peak_memories.append(peak_memory_mb)

            # 4) Line profiling (collect for averaging later)
            all_targets = []
            for fqn, fm in resolved_func_metrics.items():
                if fm.call_count > 0:
                    module, func = self._split_module_func_simple(fqn)
                    if module and func and self._valid_identifier_chain(func):
                        all_targets.append({"module": module, "func": func})

            if all_targets[:top_k_for_lines]:
                lp_code = self._build_line_profiler_wrapper_code(
                    entry_type=info["type"],
                    target=info["target"],
                    argv0=info["argv0"],
                    args=info["args"],
                    targets=all_targets[:top_k_for_lines],
                    patches_json=patches_json
                )
                lp_res = self.project.run_with_profiling(lp_code)
                if lp_res.returncode != 0:
                    errs = self._extract_patch_errors((lp_res.stdout or "") + "\n" + (lp_res.stderr or ""))
                    if errs:
                        raise RuntimeError(f"Patch apply failed: {json.dumps(errs)}")
                    logging.error("Line-profiler wrapper failed: stdout[:800]=%r stderr[:800]=%r",
                                  (lp_res.stdout or "")[:800], (lp_res.stderr or "")[:800])
                else:
                    lp_json_str = self._extract_json_block(lp_res.stdout, self.LINE_START, self.LINE_END)
                    if lp_json_str:
                        lp_payload = json.loads(lp_json_str)
                        all_line_profiles.append(lp_payload)

        # Average all metrics
        avg_total_time_ms = (sum(all_total_times) / len(all_total_times) if all_total_times else 0.0)
        avg_peak_memory_mb = (sum(all_peak_memories) / len(all_peak_memories) if all_peak_memories else 0.0)

        # Average function metrics
        averaged_func_metrics = self._average_function_metrics(all_func_metrics)

        # Recalculate fraction_of_total based on averaged times (do not average fractions)
        for fm in averaged_func_metrics.values():
            fm.fraction_of_total = ((fm.exclusive_time_ms / avg_total_time_ms) if avg_total_time_ms > 0 else 0.0)

        # Average edges
        averaged_edges = self._average_edges(all_edges)

        # Create run and persist averaged results
        seq_row = self.db.execute_sql(f"SELECT COUNT(*) AS c FROM dynamic_runs WHERE project_id = '{self.project_id}'")
        try:
            seq = (int(seq_row["c"]) if isinstance(seq_row, dict) else int(seq_row)) + 1
        except Exception:
            seq = 1
        run_id = f"{self.project_id}-r{seq}-{int(time.time())}"
        run = ProfilingRun(
            run_id=run_id,
            project_id=self.project_id,
            timestamp=datetime.utcnow().isoformat(),
            total_time_ms=avg_total_time_ms,
            function_metrics=averaged_func_metrics,
        )

        self.db.insert_dynamic_run(
            project_id=self.project_id,
            run_id=run_id,
            total_time_ms=avg_total_time_ms,
            timestamp=run.timestamp,
            peak_memory_mb=avg_peak_memory_mb,
        )

        for fqn, fm in averaged_func_metrics.items():
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

        for (caller, callee), data in averaged_edges.items():
            self.db.insert_dynamic_edge(
                project_id=self.project_id,
                run_id=run_id,
                edge={
                    "caller": caller,
                    "callee": callee,
                    "time_ms": data["time_ms"],
                    "count": data["count"],
                },
            )

        # Average and persist line profiles
        if all_line_profiles:
            averaged_line_profile = self._average_line_profiles(all_line_profiles)
            self._persist_line_timings(run_id, averaged_line_profile)

        self._apply_loop_stats_to_db(run_id)
        self.last_run = run
        return run

    # --------------------
    # Helpers
    # --------------------

    def _average_function_metrics(
            self, all_metrics: List[Dict[str, FunctionMetrics]]
    ) -> Dict[str, FunctionMetrics]:
        """Average function metrics across multiple runs"""
        if not all_metrics:
            return {}

        # Collect all FQNs
        all_fqns = set()
        for metrics_dict in all_metrics:
            all_fqns.update(metrics_dict.keys())

        averaged = {}
        for fqn in all_fqns:
            # Collect metrics for this FQN across all runs
            fqn_metrics = []
            for metrics_dict in all_metrics:
                if fqn in metrics_dict:
                    fqn_metrics.append(metrics_dict[fqn])

            if not fqn_metrics:
                continue

            # Use first occurrence as template
            first = fqn_metrics[0]
            avg_metric = FunctionMetrics(
                fqn=fqn,
                inclusive_time_ms=sum(m.inclusive_time_ms for m in fqn_metrics)
                                  / len(fqn_metrics),
                exclusive_time_ms=sum(m.exclusive_time_ms for m in fqn_metrics)
                                  / len(fqn_metrics),
                call_count=int(
                    sum(m.call_count for m in fqn_metrics) / len(fqn_metrics)
                ),
                avg_time_ms=0.0,  # Will calculate below
                fraction_of_total=0.0,  # Will be recalculated later based on averaged total time
                file_path=first.file_path,
                module_name=first.module_name,
                function_name=first.function_name,
                first_lineno=first.first_lineno,
            )

            # Recalculate avg_time_ms based on averaged values
            avg_metric.avg_time_ms = avg_metric.exclusive_time_ms / max(
                1, avg_metric.call_count
            )

            averaged[fqn] = avg_metric

        return averaged

    def _average_edges(
        self, all_edges: List[Dict[Tuple[str, str], Dict[str, Any]]]
    ) -> Dict[Tuple[str, str], Dict[str, Any]]:
        """Average edge metrics across multiple runs"""
        if not all_edges:
            return {}

        # Collect all edge keys
        all_keys = set()
        for edges_dict in all_edges:
            all_keys.update(edges_dict.keys())

        averaged = {}
        for key in all_keys:
            # Collect data for this edge across all runs
            edge_data = []
            for edges_dict in all_edges:
                if key in edges_dict:
                    edge_data.append(edges_dict[key])

            if not edge_data:
                continue

            averaged[key] = {
                "time_ms": sum(e["time_ms"] for e in edge_data) / len(edge_data),
                "count": int(sum(e["count"] for e in edge_data) / len(edge_data)),
            }

        return averaged

    def _average_line_profiles(
        self, all_profiles: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Average line profiling data across multiple runs"""
        if not all_profiles:
            return {
                "functions": [],
                "profiled_functions": [],
                "total_time_sec": 0.0,
                "debug_info": [],
            }

        # Group by function (file_path + function name)
        func_groups = {}

        for profile in all_profiles:
            for func in profile.get("functions", []):
                key = (func.get("file_path", ""), func.get("function", ""))
                if key not in func_groups:
                    func_groups[key] = []
                func_groups[key].append(func)

        averaged_funcs = []
        for (file_path, function), funcs in func_groups.items():
            # Average line timings
            line_groups = {}
            all_loop_iterations = []
            all_max_depths = []

            for func in funcs:
                all_loop_iterations.append(func.get("loop_iterations", 0))
                all_max_depths.append(func.get("max_loop_depth", 0))

                for timing in func.get("timings", []):
                    line_no = timing["line"]
                    if line_no not in line_groups:
                        line_groups[line_no] = {
                            "times": [],
                            "hits": [],
                            "preview": timing.get("preview", ""),
                            "is_loop_header": timing.get("is_loop_header", False),
                            "loop_depth": timing.get("loop_depth", 0),
                            "indentation_level": timing.get("indentation_level", 0),
                        }
                    line_groups[line_no]["times"].append(timing["time_ms"])
                    line_groups[line_no]["hits"].append(timing["hits"])

            # Build averaged timings
            averaged_timings = []
            for line_no, data in line_groups.items():
                averaged_timings.append(
                    {
                        "line": line_no,
                        "time_ms": sum(data["times"]) / len(data["times"]),
                        "hits": int(sum(data["hits"]) / len(data["hits"])),
                        "indentation_level": data["indentation_level"],
                        "preview": data["preview"],
                        "is_loop_header": data["is_loop_header"],
                        "loop_depth": data["loop_depth"],
                    }
                )

            averaged_timings.sort(key=lambda x: x["time_ms"], reverse=True)

            averaged_funcs.append(
                {
                    "file_path": file_path,
                    "function": function,
                    "timings": averaged_timings,
                    "loop_iterations": (
                        int(sum(all_loop_iterations) / len(all_loop_iterations))
                        if all_loop_iterations
                        else 0
                    ),
                    "max_loop_depth": (
                        int(sum(all_max_depths) / len(all_max_depths))
                        if all_max_depths
                        else 0
                    ),
                }
            )

        # Average total time
        avg_total_time = sum(p.get("total_time_sec", 0.0) for p in all_profiles) / len(
            all_profiles
        )

        return {
            "functions": averaged_funcs,
            "profiled_functions": (
                all_profiles[0].get("profiled_functions", []) if all_profiles else []
            ),
            "total_time_sec": avg_total_time,
            "debug_info": ["Averaged across {} runs".format(len(all_profiles))],
        }

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
    ) -> Tuple[Dict[str, FunctionMetrics], Dict[Tuple[str, str], Dict[str, Any]]]:
        """
        Traverse pyinstrument JSON and aggregate:
          - function_metrics: keyed by a temp key "module.func@L<line>", with file_path, module_name, function_name, first_lineno set.
          - edges: keyed by (caller_temp, callee_temp), with time_ms, count, plus caller_file/line and callee_file/line.

        We intentionally do NOT try to add class names here. We'll resolve to fully
        qualified FQNs later using (file_path, first_lineno) against the static DB (FQNResolver).
        """
        # Root frame
        root = session_json.get("root_frame") or session_json.get("rootFrame") or {}
        if not root:
            return {}, {}

        # Helpers
        project_root = Path(self.project.directory).resolve()

        def module_from_path(p: str) -> str:
            if not p:
                return ""
            try:
                rel = Path(p).resolve().relative_to(project_root)
                return ".".join(Path(rel).with_suffix("").parts)
            except Exception:
                # fallback: turn absolute path into a dotted-ish path
                return ".".join(Path(p).with_suffix("").parts)

        def frame_fields(frame: Dict[str, Any]) -> Tuple[str, str, str, str, int]:
            """
            Extract a temp key and relevant fields from a pyinstrument frame.

            Returns:
              temp_key: "module.func@L<line>"
              module_guess: best-effort module from file path
              func_name: raw function name (e.g., "__call__", "<lambda>")
              file_path: as reported by pyinstrument (may be absolute or relative)
              line_no: current line number inside the frame's function
            """
            file_path = (
                    frame.get("file_path")
                    or frame.get("filename")
                    or frame.get("filePath")
                    or frame.get("file")
                    or ""
            )
            # pyinstrument uses line_no; be defensive with variants
            line_no = (
                    frame.get("line_no")
                    or frame.get("lineNo")
                    or frame.get("lineno")
                    or frame.get("line")
                    or 0
            )
            try:
                line_no = int(line_no)
            except Exception:
                line_no = 0

            func_name = (
                    frame.get("function")
                    or frame.get("func")
                    or frame.get("name")
                    or "<unknown>"
            )

            module_guess = module_from_path(file_path)
            temp_key = (
                f"{module_guess}.{func_name}@L{line_no}"
                if module_guess
                else f"{func_name}@L{line_no}"
            )
            return temp_key, module_guess, func_name, str(file_path or ""), int(line_no)

        def is_synthetic(func_name: str) -> bool:
            # Frames like <listcomp>, <genexpr>, <lambda>, etc.
            try:
                return func_name.startswith("<") and func_name.endswith(">")
            except Exception:
                return False

        metrics: Dict[str, FunctionMetrics] = {}
        edges: Dict[Tuple[str, str], Dict[str, Any]] = {}

        def traverse(frame: Dict[str, Any]) -> float:
            if not frame:
                return 0.0

            # Inclusive time (seconds) for this frame from pyinstrument
            time_sec = float(frame.get("time", 0.0) or 0.0)

            # Process children first to compute exclusive time
            child_infos = []
            total_children_sec = 0.0
            for ch in frame.get("children", []):
                child_incl = traverse(ch)
                child_infos.append((ch, child_incl))
                total_children_sec += child_incl

            excl_ms = max(0.0, (time_sec - total_children_sec) * 1000.0)
            incl_ms = max(0.0, time_sec * 1000.0)

            # Current frame key + fields
            cur_key, cur_module, cur_func, cur_file, cur_line = frame_fields(frame)

            # Record function metrics (counts here are frame instances, cProfile will provide accurate call counts/time later)
            if cur_key not in metrics:
                metrics[cur_key] = FunctionMetrics(
                    fqn=cur_key,
                    inclusive_time_ms=0.0,
                    exclusive_time_ms=0.0,
                    call_count=0,
                    avg_time_ms=0.0,
                    fraction_of_total=0.0,
                    file_path=cur_file,
                    module_name=cur_module,
                    function_name=cur_func,
                    first_lineno=cur_line,
                )
            m = metrics[cur_key]
            m.inclusive_time_ms += incl_ms
            m.exclusive_time_ms += excl_ms
            m.call_count += 1  # number of times this frame appears in the tree

            # Record edges to child frames
            for ch_frame, ch_incl_sec in child_infos:
                ch_key, ch_module, ch_func, ch_file, ch_line = frame_fields(ch_frame)

                # Skip synthetic inner frames (e.g., <listcomp>, <genexpr>, <lambda>) within the same file.
                # These get resolved back to the containing function and would create a spurious self-edge.
                try:
                    same_file = (
                            cur_file
                            and ch_file
                            and Path(cur_file).resolve() == Path(ch_file).resolve()
                    )
                except Exception:
                    same_file = (cur_file == ch_file)

                if same_file and is_synthetic(ch_func):
                    continue

                k = (cur_key, ch_key)
                e = edges.setdefault(k, {"time_ms": 0.0, "count": 0})
                # Use child's inclusive time as edge weight
                e["time_ms"] += float(ch_incl_sec * 1000.0)
                e["count"] += 1

                # Attach file/line to help resolver map edges precisely
                e["caller_file"] = cur_file
                e["caller_line"] = cur_line
                e["callee_file"] = ch_file
                e["callee_line"] = ch_line

            return time_sec

        traverse(root)
        return metrics, edges

    def _apply_cprofile_to_metrics(
            self, func_metrics: Dict[str, FunctionMetrics], cp_payload: Dict[str, Any]
    ) -> Dict[str, FunctionMetrics]:
        """Merge cProfile stats (accurate ncalls/times) into FunctionMetrics, project files only.

        IMPORTANT: Replace the corresponding pyinstrument fragments for the same function
        (matched by normalized file_path + function_name, and preferring matching first_lineno)
        instead of adding a new entry, to avoid double-counting when we later resolve FQNs.
        """
        # Build an index of existing (pyinstrument) metrics by normalized file_path + function_name
        by_file_func: Dict[Tuple[str, str], List[str]] = {}
        for k, m in list(func_metrics.items()):
            file_path = m.file_path or ""
            func_name = m.function_name or ""
            try:
                norm_fp = str(Path(file_path).resolve())
            except Exception:
                norm_fp = str(file_path)
            if norm_fp and func_name:
                by_file_func.setdefault((norm_fp, func_name), []).append(k)

        for rec in cp_payload.get("functions", []):
            file_path = rec.get("file", "")
            if not self._is_project_file(file_path):
                continue

            func_name = rec.get("function", "")
            module = self._file_to_module(file_path)

            excl_ms = float(rec.get("tottime", 0.0)) * 1000.0
            incl_ms = float(rec.get("cumtime", 0.0)) * 1000.0
            try:
                ncalls = int(rec.get("ncalls", 0) or 0)
            except Exception:
                ncalls = 0

            # Try to match to existing pyinstrument fragments for the same function
            try:
                cp_norm_fp = str(Path(file_path).resolve())
            except Exception:
                cp_norm_fp = str(file_path)

            cp_first_line = 0
            try:
                cp_first_line = int(rec.get("line_no", 0) or 0)
            except Exception:
                cp_first_line = 0

            candidate_keys = by_file_func.get((cp_norm_fp, func_name), [])
            chosen_key = None

            # Prefer a candidate whose first_lineno matches cProfile's first line, if provided
            if candidate_keys and cp_first_line:
                for k in candidate_keys:
                    m = func_metrics.get(k)
                    if m and int(m.first_lineno or 0) == cp_first_line:
                        chosen_key = k
                        break

            # Otherwise, pick any candidate for this (file, func) pair
            if not chosen_key and candidate_keys:
                chosen_key = candidate_keys[0]

            if chosen_key:
                # Defensive check: key might have been deleted in a previous iteration
                if chosen_key not in func_metrics:
                    continue

                # Update the chosen existing entry with authoritative cProfile numbers
                m = func_metrics[chosen_key]
                m.inclusive_time_ms = incl_ms
                m.exclusive_time_ms = excl_ms
                m.call_count = ncalls
                m.avg_time_ms = excl_ms / max(1, ncalls)
                m.module_name = module
                m.function_name = func_name
                m.fqn = f"{module}.{func_name}"
                m.file_path = str(file_path)
                if cp_first_line:
                    m.first_lineno = cp_first_line

                # Remove any other pyinstrument fragments for the same function to avoid double counting
                for k in candidate_keys:
                    if k != chosen_key and k in func_metrics:
                        del func_metrics[k]
            else:
                # No existing pyinstrument entry matched; create a new entry for this cProfile function
                fqn = f"{module}.{func_name}"
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
                    first_lineno=cp_first_line,
                )

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
    def _build_pyinstrument_wrapper_code(self, entry_type: str, target: str, argv0: str, args: List[str], patches_json: str) -> str:
        project_dir = str(self.project.directory.resolve())
        header = textwrap.dedent(f"""\
        import sys, time, json, importlib, pathlib
        from pyinstrument import Profiler
        try:
            from pyinstrument.renderers.jsonrenderer import JSONRenderer
        except Exception:
            from pyinstrument.renderers import JSONRenderer

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

        def _module_name_from_path(project_dir, path):
            p = pathlib.Path(path).resolve()
            proj = pathlib.Path(project_dir).resolve()
            try:
                rel = p.relative_to(proj)
                parts = list(rel.parts)
                if parts[-1] == "__init__.py":
                    parts = parts[:-1]
                else:
                    parts[-1] = parts[-1].rsplit(".", 1)[0]
                return ".".join(parts)
            except Exception:
                return p.stem

        MODULE_NAME = ENTRY_TARGET if ENTRY_TYPE == "module" else _module_name_from_path(PROJECT_DIR, ENTRY_TARGET)
        """)
        prologue = self._patch_prologue(patches_json)
        body = textwrap.dedent("""\
        mod = importlib.import_module(MODULE_NAME)

        # Apply patches BEFORE timing
        if PATCHES:
            _apply_patches(PATCHES)

        prof = Profiler(interval=0.0001)
        t0 = time.perf_counter()
        prof.start()
        try:
            if hasattr(mod, "main"):
                mod.main()
        finally:
            prof.stop()
            t1 = time.perf_counter()

        renderer = JSONRenderer()
        payload = {"session": json.loads(renderer.render(prof.last_session)), "total_time_sec": (t1 - t0)}
        print(START, flush=True); print(json.dumps(payload), flush=True); print(END, flush=True)
        """)
        return header + prologue + "\n" + body

    def _build_cprofile_wrapper_code(self, entry_type: str, target: str, argv0: str, args: List[str], patches_json: str) -> str:
        project_dir = str(self.project.directory.resolve())
        header = textwrap.dedent(f"""\
        import sys, time, json, importlib, pathlib, cProfile, pstats

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

        def _module_name_from_path(project_dir, path):
            p = pathlib.Path(path).resolve()
            proj = pathlib.Path(project_dir).resolve()
            try:
                rel = p.relative_to(proj)
                parts = list(rel.parts)
                if parts[-1] == "__init__.py":
                    parts = parts[:-1]
                else:
                    parts[-1] = parts[-1].rsplit(".", 1)[0]
                return ".".join(parts)
            except Exception:
                return p.stem

        MODULE_NAME = ENTRY_TARGET if ENTRY_TYPE == "module" else _module_name_from_path(PROJECT_DIR, ENTRY_TARGET)
        """)
        prologue = self._patch_prologue(patches_json)
        body = textwrap.dedent("""\
        mod = importlib.import_module(MODULE_NAME)

        if PATCHES:
            _apply_patches(PATCHES)

        pr = cProfile.Profile()
        t0 = time.perf_counter()
        pr.enable()
        try:
            if hasattr(mod, "main"):
                mod.main()
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
            out.append({"file": filename, "line_no": int(lineno), "function": funcname, "ncalls": ncalls, "tottime": float(tt), "cumtime": float(ct)})

        payload = {"functions": out, "total_time_sec": (t1 - t0)}
        print(START, flush=True); print(json.dumps(payload), flush=True); print(END, flush=True)
        """)
        return header + prologue + "\n" + body

    def _build_memory_wrapper_code(self, entry_type: str, target: str, argv0: str, args: List[str], patches_json: str) -> str:
        project_dir = str(self.project.directory.resolve())
        header = textwrap.dedent(f"""\
        import sys, time, json, importlib, pathlib, gc, tracemalloc

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

        def _module_name_from_path(project_dir, path):
            p = pathlib.Path(path).resolve()
            proj = pathlib.Path(project_dir).resolve()
            try:
                rel = p.relative_to(proj)
                parts = list(rel.parts)
                if parts[-1] == "__init__.py":
                    parts = parts[:-1]
                else:
                    parts[-1] = parts[-1].rsplit(".", 1)[0]
                return ".".join(parts)
            except Exception:
                return p.stem

        MODULE_NAME = ENTRY_TARGET if ENTRY_TYPE == "module" else _module_name_from_path(PROJECT_DIR, ENTRY_TARGET)
        """)
        prologue = self._patch_prologue(patches_json)
        body = textwrap.dedent("""\
        mod = importlib.import_module(MODULE_NAME)

        if PATCHES:
            _apply_patches(PATCHES)

        gc.collect()
        tracemalloc.start()

        t0 = time.perf_counter()
        try:
            if hasattr(mod, "main"):
                mod.main()
        finally:
            t1 = time.perf_counter()
            current, peak = tracemalloc.get_traced_memory()
            peak_mb = peak / (1024 * 1024)
            tracemalloc.stop()

            payload = {"peak_memory_mb": peak_mb, "total_time_sec": (t1 - t0)}
            print(START, flush=True); print(json.dumps(payload), flush=True); print(END, flush=True)
        """)
        return header + prologue + "\n" + body

    def _build_line_profiler_wrapper_code(
            self,
            entry_type: str,
            target: str,
            argv0: str,
            args: List[str],
            targets: List[Dict[str, str]],
            patches_json: str,
    ) -> str:
        project_dir = str(self.project.directory.resolve())
        targets_payload = [{"module": t["module"], "func": t["func"]} for t in targets]

        header = textwrap.dedent(f"""\
        import sys, time, json, importlib, pathlib, inspect, ast
        from line_profiler import LineProfiler

        ENTRY_TYPE = {repr(entry_type)}
        ENTRY_TARGET = {repr(target)}
        ENTRY_ARGS = {repr(list(args or []))}
        ARGV0 = {repr(argv0)}
        TARGET_FUNCS = {json.dumps(targets_payload)}
        PROJECT_DIR = {repr(project_dir)}
        START = {repr(self.LINE_START)}
        END = {repr(self.LINE_END)}

        if PROJECT_DIR not in sys.path:
            sys.path.insert(0, PROJECT_DIR)

        sys.argv = [ARGV0] + list(ENTRY_ARGS)

        def _module_name_from_path(project_dir, path):
            p = pathlib.Path(path).resolve()
            proj = pathlib.Path(project_dir).resolve()
            try:
                rel = p.relative_to(proj)
                parts = list(rel.parts)
                if parts[-1] == "__init__.py":
                    parts = parts[:-1]
                else:
                    parts[-1] = parts[-1].rsplit(".", 1)[0]
                return ".".join(parts)
            except Exception:
                return p.stem

        MODULE_NAME = ENTRY_TARGET if ENTRY_TYPE == "module" else _module_name_from_path(PROJECT_DIR, ENTRY_TARGET)
        """)
        prologue = self._patch_prologue(patches_json)
        body = textwrap.dedent("""\
        lp = LineProfiler()
        debug_info = []
        func_info_map = {}

        def detect_loop_lines(file_path):
            loop_header_lines = set()
            loop_body_lines = {}
            try:
                with open(file_path, 'r') as f:
                    source = f.read()
                    lines = source.split('\\n')
                tree = ast.parse(source)
                class LoopVisitor(ast.NodeVisitor):
                    def __init__(self): self.loop_stack = []
                    def visit_For(self, node):
                        loop_header_lines.add(node.lineno); self.loop_stack.append(node.lineno)
                        for stmt in ast.walk(node):
                            if hasattr(stmt, 'lineno'):
                                loop_body_lines[stmt.lineno] = len(self.loop_stack)
                        self.generic_visit(node); self.loop_stack.pop()
                    def visit_While(self, node):
                        loop_header_lines.add(node.lineno); self.loop_stack.append(node.lineno)
                        for stmt in ast.walk(node):
                            if hasattr(stmt, 'lineno'):
                                loop_body_lines[stmt.lineno] = len(self.loop_stack)
                        self.generic_visit(node); self.loop_stack.pop()
                    def visit_ListComp(self, node):
                        loop_header_lines.add(node.lineno); loop_body_lines[node.lineno] = len(self.loop_stack) + 1; self.generic_visit(node)
                    def visit_DictComp(self, node):
                        loop_header_lines.add(node.lineno); loop_body_lines[node.lineno] = len(self.loop_stack) + 1; self.generic_visit(node)
                    def visit_SetComp(self, node):
                        loop_header_lines.add(node.lineno); loop_body_lines[node.lineno] = len(self.loop_stack) + 1; self.generic_visit(node)
                LoopVisitor().visit(tree)
                for i, line in enumerate(lines, 1):
                    s = line.strip()
                    if (s.startswith('for ') or s.startswith('while ') or (' for ' in line and any(b in line for b in ['[', '(', '{']))):
                        loop_header_lines.add(i)
                return loop_header_lines, loop_body_lines
            except Exception as e:
                debug_info.append(f"Error detecting loops in {file_path}: {e}")
                return set(), {}

        def add_target(module_name, func_chain):
            try:
                mod_t = importlib.import_module(module_name)
                obj = mod_t
                for attr in func_chain.split('.'):
                    obj = getattr(obj, attr)
                if inspect.isfunction(obj) or inspect.ismethod(obj):
                    func_obj = obj if inspect.isfunction(obj) else obj.__func__
                    lp.add_function(func_obj)
                    try:
                        file_path = inspect.getfile(func_obj)
                        func_name = func_obj.__name__
                        first_line = func_obj.__code__.co_firstlineno
                        lp_key = (file_path, first_line, func_name)
                        loop_header_lines, loop_body_lines = detect_loop_lines(file_path)
                        func_info_map[lp_key] = {
                            'file_path': file_path,
                            'func_name': func_name,
                            'module_name': module_name,
                            'func_chain': func_chain,
                            'first_line': first_line,
                            'loop_header_lines': loop_header_lines,
                            'loop_body_lines': loop_body_lines
                        }
                        return True, module_name, func_chain
                    except Exception:
                        return False, module_name, func_chain
                return False, module_name, func_chain
            except Exception:
                return False, module_name, func_chain

        added = []
        for spec in TARGET_FUNCS:
            ok, m, f = add_target(spec['module'], spec['func'])
            if ok:
                added.append({'module': m, 'func': f})

        # Import actual entry module and apply patches
        mod = importlib.import_module(MODULE_NAME)
        if PATCHES:
            _apply_patches(PATCHES)

        t0 = time.perf_counter()
        # Run the actual program under line_profiler using runctx (portable API)
        globs = {'mod': mod}
        lp.runctx("mod.main()", globs, {})
        t1 = time.perf_counter()

        stats = lp.get_stats()
        unit = getattr(stats, "unit", 1.0) or 1.0
        out_funcs = []

        for key, timings in stats.timings.items():
            if isinstance(key, tuple) and len(key) == 3:
                file_path, first_line, func_name = key
                info = func_info_map.get(key, {})
                loop_header_lines = info.get('loop_header_lines', set())
                loop_body_lines = info.get('loop_body_lines', {})
            else:
                file_path = "<unknown>"; func_name = "<unknown>"
                loop_header_lines = set(); loop_body_lines = {}

            lines = []
            loop_iterations = 0
            max_loop_depth = 0
            for lineno, nhits, t in timings:
                time_ms = float(t) * float(unit) * 1000.0
                is_loop_header = lineno in loop_header_lines
                loop_depth = loop_body_lines.get(lineno, 0)
                if is_loop_header:
                    loop_iterations += nhits
                    max_loop_depth = max(max_loop_depth, loop_depth)
                lines.append({
                    "line": int(lineno),
                    "time_ms": time_ms,
                    "hits": int(nhits),
                    "indentation_level": 0,
                    "preview": "",
                    "is_loop_header": is_loop_header,
                    "loop_depth": loop_depth
                })

            if lines:
                lines.sort(key=lambda x: x["time_ms"], reverse=True)
                out_funcs.append({
                    "file_path": file_path,
                    "function": func_name,
                    "timings": lines,
                    "loop_iterations": loop_iterations,
                    "max_loop_depth": max_loop_depth
                })

        payload = {
            "functions": out_funcs,
            "profiled_functions": added,
            "total_time_sec": (t1 - t0),
            "debug_info": debug_info
        }
        print(START, flush=True)
        print(json.dumps(payload), flush=True)
        print(END, flush=True)
        """)
        return header + prologue + "\n" + body

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


    def _patch_prologue(self, patches_json: str) -> str:
        # Defines _apply_patches without auto-executing it.
        # Preserves filename + first line for profilers/debugger,
        # pre-injects typing symbols for annotations, and returns the correct function
        # by matching the expected name from the FQN (avoids grabbing imported callables).
        import textwrap
        return textwrap.dedent(f"""\
        import json, importlib, inspect, sys

        # Preload typing symbols for annotation references (e.g., List, Tuple, Dict)
        try:
            import typing as _typing
            _TYPING_NS = dict(_typing.__dict__)
        except Exception:
            _TYPING_NS = {{}}

        PATCHES = json.loads({repr(patches_json)})

        def _compile_func(src, filename, first_lineno, expected_name):
            prefix = "\\n" * max(0, int(first_lineno or 1) - 1)
            code_str = prefix + (src or "")
            code_obj = compile(code_str, filename or "<patched>", "exec")
            ns = {{}}
            ns.update(_TYPING_NS)
            exec(code_obj, ns, ns)

            # 1) Exact name match in namespace
            cand = ns.get(expected_name)
            if inspect.isfunction(cand) or inspect.iscoroutinefunction(cand):
                return cand

            # 2) Any function whose __name__ matches expected_name
            for v in ns.values():
                if (inspect.isfunction(v) or inspect.iscoroutinefunction(v)) and getattr(v, "__name__", None) == expected_name:
                    return v

            # 3) Fallback: any function compiled from this code chunk
            funcs = [v for v in ns.values() if inspect.isfunction(v) or inspect.iscoroutinefunction(v)]
            if funcs:
                from_this_file = [f for f in funcs if getattr(f, "__code__", None) and f.__code__.co_filename == (filename or "<patched>")]
                if from_this_file:
                    return from_this_file[-1]
                return funcs[-1]
            return None

        def _apply_patches(patches):
            for p in patches:
                fqn = p.get("fqn") or ""
                src = p.get("src")
                is_method = bool(p.get("is_method"))
                is_staticmethod = bool(p.get("is_staticmethod"))
                is_classmethod_flag = bool(p.get("is_classmethod"))
                is_property_flag = bool(p.get("is_property"))
                file_path = p.get("abs_file_path") or p.get("file_path") or "<string>"
                start_line = int(p.get("start_line") or 1)

                parts = fqn.split(".")
                expected_name = parts[-1] if parts else None

                try:
                    new_fn = _compile_func(src, file_path, start_line, expected_name)
                    if new_fn is None:
                        raise RuntimeError("No function object found in replacement_source")

                    if is_method:
                        module_name = ".".join(parts[:-2]); cls_name = parts[-2]; attr = parts[-1]
                    else:
                        module_name = ".".join(parts[:-1]); cls_name = None; attr = parts[-1]

                    mod = importlib.import_module(module_name) if module_name else None
                    target = getattr(mod, cls_name) if cls_name else mod

                    if is_staticmethod:
                        patched = staticmethod(new_fn)
                    elif is_classmethod_flag:
                        patched = classmethod(new_fn)
                    elif is_property_flag:
                        orig = getattr(target, attr, None)
                        if isinstance(orig, property):
                            patched = property(new_fn, orig.fset, orig.fdel, new_fn.__doc__ or getattr(orig, "__doc__", None))
                        else:
                            patched = new_fn
                    else:
                        patched = new_fn

                    setattr(target, attr, patched)
                except Exception as _e:
                    print({repr(self.PATCH_ERR_MARK)} + json.dumps({{"fqn": fqn, "error": str(_e)}}), flush=True)
                    raise
        """)

    def _extract_patch_errors(self, text: str):
        out = []
        for line in (text or "").splitlines():
            if line.startswith(self.PATCH_ERR_MARK):
                try:
                    out.append(json.loads(line[len(self.PATCH_ERR_MARK):]))
                except Exception:
                    out.append({"fqn": None, "error": line})
        return out

    def _build_warmup_wrapper_code(self, entry_type: str, target: str, argv0: str, args: List[str], patches_json: str) -> str:
        project_dir = str(self.project.directory.resolve())
        prologue = self._patch_prologue(patches_json)
        code = f"""
        import sys, runpy

        PROJECT_DIR = {repr(project_dir)}
        if PROJECT_DIR not in sys.path:
            sys.path.insert(0, PROJECT_DIR)

        ENTRY_TYPE = {repr(entry_type)}
        ENTRY_TARGET = {repr(target)}
        ENTRY_ARGS = {repr(list(args or []))}
        ARGV0 = {repr(argv0)}

        sys.argv = [ARGV0] + list(ENTRY_ARGS)

        # ----- PATCHES BEGIN -----
        {prologue}
        # ----- PATCHES END -----

        if ENTRY_TYPE == "script":
            runpy.run_path(ENTRY_TARGET, run_name="__main__")
        else:
            runpy.run_module(ENTRY_TARGET, run_name="__main__")
        """
        return textwrap.dedent(code)

    def _build_patch_only_wrapper_code(self, patches_json: str) -> str:
        project_dir = str(self.project.directory.resolve())
        header = textwrap.dedent(f"""\
        import sys
        PROJECT_DIR = {repr(project_dir)}
        if PROJECT_DIR not in sys.path:
            sys.path.insert(0, PROJECT_DIR)
        """)
        prologue = self._patch_prologue(patches_json)
        body = textwrap.dedent("""\
        # Apply patches and exit
        if PATCHES:
            _apply_patches(PATCHES)
        """)
        wrapper = header + prologue + "\n" + body + "\n"
        compile(wrapper, "<patch_only_wrapper>", "exec")
        return wrapper