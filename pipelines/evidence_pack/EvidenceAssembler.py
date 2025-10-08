import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import List, Dict, Tuple, Optional

from pipelines.code_analysis import Project, ChunkDatabase
import textwrap

def _parse_fqn(fqn: str):
    """Return (module, class_name|None, func_name) from a fully resolved FQN."""
    if not fqn:
        return "", None, ""
    parts = fqn.split(".")
    if parts[-1] == "<module>":
        return ".".join(parts[:-1]), None, "<module>"
    if len(parts) >= 3 and parts[-2] and parts[-2][0].isupper():
        return ".".join(parts[:-2]), parts[-2], parts[-1]
    return ".".join(parts[:-1]), None, parts[-1]


def _is_noise_fqn(fqn: str) -> bool:
    if not fqn:
        return True
    if fqn == "[self]":
        return True
    if fqn.startswith("<built-in>"):
        return True
    if fqn.startswith("<frozen "):
        return True
    return False


def _edge_label(parent_fqn: str, child_fqn: str, project_prefix: str) -> str:
    """Friendly label for child under parent."""
    _, parent_cls, _ = _parse_fqn(parent_fqn)
    child_mod, child_cls, child_func = _parse_fqn(child_fqn)

    if child_func == "<module>":
        return "<module>"

    # Inside project, method → method: show self.method
    if parent_cls and child_cls and child_mod.startswith(project_prefix):
        return f"self.{child_func}"

    if child_cls:
        return f"{child_cls}.{child_func}"
    return child_func


def _node_label(fqn: str) -> str:
    """Label for the node itself."""
    _, cls, func = _parse_fqn(fqn)
    return f"{cls}.{func}" if cls else func


def get_full_project_call_tree(
        db: ChunkDatabase,
        project_id: str,
        run_id: str,
        project_prefix: Optional[str] = None,
        include_external: bool = False,    # keep False to show only your package
        max_roots: int = 50,               # just a safety; set high
        max_depth: Optional[int] = None,   # None == unlimited
        hide_module_nodes: bool = True,    # drop ....<module> nodes from the tree
        hide_self_edges: bool = True,      # drop caller==callee edges
) -> List[Dict]:
    """
    Build a full execution tree (a forest under the hood) from dynamic edges.
    - Roots are in-project nodes with no in-project parents (ignoring <module> and external parents).
    - Filters “noise” like [self], <built-in>, <frozen ...>, and optionally ....<module>.
    - Optionally hides self-edges (caller==callee), which often appear as noise.
    - Each node: {fqn, exclusive_ms, inclusive_ms, fraction, calls, children[, recursion]}.
    """
    project_prefix = project_prefix or project_id

    def in_pkg(f: str) -> bool:
        return isinstance(f, str) and f.startswith(project_prefix + ".")

    def is_module_node(f: str) -> bool:
        return isinstance(f, str) and f.endswith(".<module>")

    def is_noise_fqn(f: str) -> bool:
        if not f:
            return True
        if f == "[self]":
            return True
        if f.startswith("<built-in>"):
            return True
        if f.startswith("<frozen "):
            return True
        return False

    # Load function metrics
    rows = db.execute_sql(
        f"""
        SELECT fqn, exclusive_time_ms, inclusive_time_ms, call_count, fraction_of_total
        FROM dynamic_functions
        WHERE project_id = '{project_id}' AND run_id = '{run_id}'
        """
    )
    if not rows:
        return []

    # Keep only in-project functions; optionally drop module nodes
    func: Dict[str, Dict] = {}
    for r in rows:
        fqn = r["fqn"]
        if is_noise_fqn(fqn):
            continue
        if not include_external and not in_pkg(fqn):
            continue
        if hide_module_nodes and is_module_node(fqn):
            continue
        func[fqn] = r

    if not func:
        return []

    # Load edges
    raw_edges = db.execute_sql(
        f"""
        SELECT caller, callee, time_ms, count
        FROM dynamic_edges
        WHERE project_id = '{project_id}' AND run_id = '{run_id}'
        """
    )

    # Build adjacency (filtered)
    from collections import defaultdict

    children: Dict[str, List[Tuple[str, float, int]]] = defaultdict(list)
    parents: Dict[str, List[str]] = defaultdict(list)

    for e in raw_edges or []:
        a, b = e["caller"], e["callee"]
        if is_noise_fqn(a) or is_noise_fqn(b):
            continue
        if hide_module_nodes and (is_module_node(a) or is_module_node(b)):
            continue
        if hide_self_edges and a == b:
            continue
        if not include_external and (not in_pkg(a) or not in_pkg(b)):
            continue
        if a not in func or b not in func:
            continue

        w = float(e.get("time_ms", 0.0) or 0.0)
        c = int(e.get("count", 0) or 0)
        children[a].append((b, w, c))
        parents[b].append(a)

    # Nodes present after filtering
    nodes = set(func.keys())

    # Choose roots: in-project nodes with no in-project, non-module parents
    def has_in_pkg_parent(n: str) -> bool:
        return any(in_pkg(p) and not is_module_node(p) for p in parents.get(n, []))

    roots = [n for n in nodes if in_pkg(n) and not has_in_pkg_parent(n)]

    # Fallback: hottest nodes if no roots detected
    if not roots:
        roots = sorted(nodes, key=lambda n: func[n]["inclusive_time_ms"], reverse=True)[
            :max_roots
        ]

    # Sort children deterministically: edge time desc, then child inclusive desc, then name
    for p in list(children.keys()):
        children[p].sort(
            key=lambda t: (t[1], func[t[0]]["inclusive_time_ms"], t[0]), reverse=True
        )

    # Limit to nodes reachable from selected roots
    reachable = set()
    for r in roots:
        stack = [r]
        seen = set()
        while stack:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u)
            reachable.add(u)
            for v, _, _ in children.get(u, []):
                if v not in seen:
                    stack.append(v)

    roots = [r for r in roots if r in reachable]
    roots.sort(key=lambda n: func[n]["inclusive_time_ms"], reverse=True)
    roots = roots[:max_roots]

    # DFS with recursion detection and optional max_depth
    def build_tree(root: str) -> Dict:
        def dfs(u: str, onstack: set, depth: int) -> Dict:
            node = {
                "fqn": u,
                "exclusive_ms": float(func[u]["exclusive_time_ms"]),
                "inclusive_ms": float(func[u]["inclusive_time_ms"]),
                "fraction": float(func[u]["fraction_of_total"]),
                "calls": int(func[u]["call_count"]),
                "children": [],
            }

            if max_depth is not None and depth >= max_depth:
                return node

            if u in onstack:  # cycle detected; mark recursion and stop
                node["recursion"] = True
                node["children"] = []
                return node

            onstack = set(onstack)
            onstack.add(u)

            for v, _, _ in children.get(u, []):
                if v not in reachable or v not in func:
                    continue
                if v in onstack:
                    # Show a recursion stub (no expansion)
                    node["children"].append(
                        {
                            "fqn": v,
                            "exclusive_ms": float(func[v]["exclusive_time_ms"]),
                            "inclusive_ms": float(func[v]["inclusive_time_ms"]),
                            "fraction": float(func[v]["fraction_of_total"]),
                            "calls": int(func[v]["call_count"]),
                            "children": [],
                            "recursion": True,
                        }
                    )
                else:
                    node["children"].append(dfs(v, onstack, depth + 1))

            return node

        return dfs(root, set(), 0)

    tree = [build_tree(r) for r in roots]
    return tree

def format_full_tree(tree: List[Dict]) -> str:
    """
    Format the call tree with ASCII branches, e.g.:

    selection_sorter.main [0.0/182.0ms] (0.0%, 1 calls)/
    ├→ selection_sorter.timed_call [0.0/176.4ms] (0.0%, 1 calls)/
    │   └→ selection_sorter.selection_sort [176.2/176.4ms] (94.9%, 1 calls)
    └→ selection_sorter.generate_numbers [0.4/8.7ms] (0.2%, 2 calls)
    """
    if not tree:
        return ""

    lines: List[str] = []

    def label(n: Dict) -> str:
        s = f'{n["fqn"]} [{n["exclusive_ms"]:.1f}/{n["inclusive_ms"]:.1f}ms] ({n["fraction"]*100:.1f}%, {n["calls"]} calls)'
        if n.get("recursion"):
            s += " ↻"
        return s

    def emit(n: Dict, prefix: str = "", is_root: bool = False, is_last: bool = True):
        has_kids = bool(n.get("children"))
        text = label(n) + ("/" if has_kids else "")

        if is_root:
            lines.append(text)
        else:
            connector = "└→" if is_last else "├→"
            lines.append(f"{prefix}{connector} {text}")

        child_prefix = prefix + ("    " if is_last else "│   ")
        ch = n.get("children", [])
        for i, c in enumerate(ch):
            emit(c, child_prefix, False, i == len(ch) - 1)

    for i, root in enumerate(tree):
        emit(root, "", True, i == len(tree) - 1)

    return "\n".join(lines)


def get_hot_paths(
        db: ChunkDatabase,
        project_id: str,
        run_id: str,
        top_n: int = 5,
        project_prefix: str | None = None,
        include_external_leaf: bool = True,   # new: append a single external callee leaf
) -> List[Dict]:
    project_prefix = project_prefix or project_id

    def in_pkg(f: str) -> bool:
        return isinstance(f, str) and f.startswith(project_prefix + ".")

    def is_module_node(f: str) -> bool:
        return isinstance(f, str) and f.endswith(".<module>")

    # Load top bottlenecks (grab extra to allow filtering)
    bottlenecks = db.execute_sql(
        f"""
        SELECT fqn, exclusive_time_ms, fraction_of_total
        FROM dynamic_functions
        WHERE project_id = '{project_id}' AND run_id = '{run_id}'
        ORDER BY exclusive_time_ms DESC
        LIMIT {top_n*5}
        """
    ) or []

    # Filter out noise, non-project, and module nodes; also skip tiny bottlenecks (<0.1ms)
    min_bottleneck_ms = 0.1
    bottlenecks = [
        b for b in bottlenecks
        if b.get("fqn")
           and not _is_noise_fqn(b["fqn"])
           and in_pkg(b["fqn"])
           and not is_module_node(b["fqn"])
           and float(b.get("exclusive_time_ms") or 0.0) >= min_bottleneck_ms
    ]

    # Load edges (we’ll build both parent links for in-project traversal and
    # a full children map to optionally add a single external leaf at the end)
    edges = db.execute_sql(
        f"""
        SELECT caller, callee, time_ms
        FROM dynamic_edges
        WHERE project_id = '{project_id}' AND run_id = '{run_id}'
        """
    ) or []

    from collections import defaultdict
    parents = defaultdict(list)       # child -> [(parent, weight)] (in-project only)
    children_all = defaultdict(list)  # caller -> [(callee, weight)] (project + external)

    for e in edges:
        c, d = e["caller"], e["callee"]
        if _is_noise_fqn(c) or _is_noise_fqn(d):
            continue
        if c == d:
            continue
        w = float(e.get("time_ms", 0.0) or 0.0)

        # Build children map first (for optional external leaf)
        if not is_module_node(c) and not is_module_node(d):
            children_all[c].append((d, w))

        # Parent links only for in-project chain (and no ....<module>)
        if in_pkg(c) and in_pkg(d) and not is_module_node(c) and not is_module_node(d):
            parents[d].append((c, w))

    hot_paths: List[Dict] = []
    seen_targets = set()

    for b in bottlenecks:
        fqn = b["fqn"]
        if fqn in seen_targets:
            continue

        # Build a linear path upward by picking the strongest incoming edge each step (in-project only)
        path = [fqn]
        seen = {fqn}
        cur = fqn
        while cur in parents and parents[cur]:
            p = max(parents[cur], key=lambda t: t[1])[0]
            if p in seen:
                break
            path.append(p)
            seen.add(p)
            cur = p

        path.reverse()  # root -> target

        # Keep only meaningful, in-project paths (at least one edge)
        if len(path) < 2:
            continue

        ext_leaf = None
        if include_external_leaf:
            # Pick the strongest external callee from the final in-project node
            leaf = path[-1]
            cands = [
                (d, w) for (d, w) in children_all.get(leaf, [])
                if not in_pkg(d) and not is_module_node(d) and not _is_noise_fqn(d)
            ]
            if cands:
                ext_leaf = max(cands, key=lambda t: t[1])[0]

        hot_paths.append(
            {
                "path": path,
                "bottleneck_ms": float(b["exclusive_time_ms"]),
                "bottleneck_fraction": float(b["fraction_of_total"]),
                "external_leaf": ext_leaf,  # may be None
            }
        )
        seen_targets.add(fqn)

        if len(hot_paths) >= top_n:
            break

    return hot_paths


def format_hot_paths_for_llm(hot_paths: List[Dict], project_prefix: str) -> str:
    lines = []
    for i, info in enumerate(hot_paths, 1):
        path = info.get("path", []) or []
        if len(path) < 2:
            continue

        lines.append(
            f"\nHot Path #{i} ({info['bottleneck_fraction']*100:.1f}% of runtime, {info['bottleneck_ms']:.1f}ms)"
        )

        # Root
        lines.append(path[0])

        # Linear chain: always use "└→" (a hot path is not a branching tree)
        for j in range(1, len(path)):
            indent = "    " * (j - 1)
            lines.append(f"{indent}└→ {path[j]}")

        # Optional external leaf (do not expand further)
        ext = info.get("external_leaf")
        if ext:
            indent = "    " * (len(path) - 1)
            lines.append(f"{indent}└→ {ext} [external]")

    return "\n".join(lines).lstrip()


def format_functions_as_markdown(functions_data: Dict) -> str:
    """Converts the function statistics dictionary into a readable Markdown format."""
    lines = []

    for fqn, data in functions_data.items():
        lines.append(f"### {fqn}")

        # Parameters and Return
        params = ", ".join(data.get('parameters', [])) or "None"
        lines.append(f"**Parameters:** `{params}`")
        lines.append(f"**Return Annotation:** `{data.get('return_annotation') or 'None'}`")

        # Decorators
        decorators = ", ".join(data.get('decorators', [])) or "None"
        lines.append(f"**Decorators:** `{decorators}`")

        # Docstring
        docstring = data.get('docstring', '') or None
        if docstring:
            lines.append("**Docstring:**")
            for line in docstring.split('\n'):
                lines.append(f"> {line.strip()}")
        else:
            lines.append("**Docstring:** `None`")

        # Slowness Prediction (from embedding_predictions)
        pred = data.get('ml_prediction', {}) or {}
        p_slow = pred.get('p_slow')
        if p_slow is None:
            lines.append("**Slowness Prediction:** `None`")
        else:
            likely_slow =  p_slow >= 0.5
            label = "Likely Slow" if likely_slow else "Likely OK"
            lines.append(f"**Bottleneck Prediction:** {p_slow:.3f}")

        # Merged Features
        lines.append("\n**Features:**")
        features = {
            **data.get('static_features', {}),
            **data.get('dynamic_features', {})
        }

        for key, value in features.items():
            # Prettify the key
            key_pretty = key.replace('_', ' ').title()

            # Format the value for better readability
            if value is None:
                value_pretty = "`None`"
            elif key == 'fraction_of_total':
                value_pretty = f"{value * 100:.1f}%"
            elif 'time_ms' in key:
                value_pretty = f"{value:.2f} ms"
            elif 'iterations' in key:
                value_pretty = f"{int(value):,}" if value else "0"
            else:
                value_pretty = f"`{value}`"

            lines.append(f"- **{key_pretty}:** {value_pretty}")

        lines.append("\n---")  # Separator between functions

    return "\n".join(lines)

def assemble_evidence_pack(project: Project, db_path: Path = Path("chunks.db")):
    logging.info(
        f'=== Assembling EvidencePack for Project: {project.config["project"]["id"]} ==='
    )
    db = ChunkDatabase(db_path)

    # latest run id
    run_row = db.execute_sql(
        f"""
        SELECT run_id
        FROM dynamic_runs
        WHERE project_id = '{project.config["project"]["id"]}'
        ORDER BY timestamp DESC LIMIT 1
        """
    )
    if not run_row:
        return "No runs found."

    if isinstance(run_row, dict):
        run_id = run_row.get("run_id")
    elif isinstance(run_row, list) and run_row:
        run_id = run_row[0]["run_id"] if isinstance(run_row[0], dict) else run_row[0]
    else:
        run_id = str(run_row)

    project_prefix = project.config["project"]["id"]

    tree = get_full_project_call_tree(
        db,
        project_id=project_prefix,
        run_id=run_id,
        project_prefix=project_prefix,
        include_external=False,  # only your package
        max_roots=50,            # large but finite
        max_depth=None,          # unlimited
        hide_module_nodes=True,  # drop ....<module> nodes
        hide_self_edges=True,    # drop recursion self-edges (noise)
    )
    call_tree_text = format_full_tree(tree).strip()

    # Hottest paths (with a single [external] leaf if present)
    hot_paths = get_hot_paths(
        db, project_prefix, run_id, top_n=3, project_prefix=project_prefix, include_external_leaf=True
    )
    hot_paths_text = format_hot_paths_for_llm(hot_paths, project_prefix).strip()

    # Totals
    row = db.execute_sql(
        f"""
        SELECT total_time_ms, peak_memory_mb
        FROM dynamic_runs
        WHERE project_id = '{project_prefix}' AND run_id = '{run_id}'
        """
    )
    if isinstance(row, list):
        row = row[0] if row else None
    total_runtime = float(row["total_time_ms"]) if row else 0.0
    peak_memory_mb = float(row["peak_memory_mb"]) if row else 0.0

    count_row = db.execute_sql(
        f"SELECT COUNT(*) AS n FROM functions WHERE project_id = '{project_prefix}'"
    )
    if isinstance(count_row, list):
        total_n_functions = int(count_row[0]["n"]) if count_row else 0
    elif isinstance(count_row, dict):
        total_n_functions = int(count_row.get("n", 0))
    else:
        total_n_functions = int(count_row) if count_row else 0

    # Function stats (your existing join)
    all_functions_with_metrics_raw = db.execute_sql(
        f"""
    SELECT 
        f.function_name, f.fqn, f.parameters, f.return_annotation, f.decorators, f.docstring, f.static_features,
        df.inclusive_time_ms, df.exclusive_time_ms, df.call_count, df.fraction_of_total, df.loop_iterations_total,
        ep.p_slow, ep.is_slow
    FROM functions f
    JOIN dynamic_functions df 
        ON f.fqn = df.fqn AND df.run_id = '{run_id}'
    LEFT JOIN embedding_predictions ep
        ON ep.fqn = f.fqn AND ep.project_id = '{project_prefix}'
    WHERE f.project_id = '{project_prefix}'
    """
    ) or []

    all_functions_with_metrics = {}
    for function in all_functions_with_metrics_raw:
        static_features = json.loads(function["static_features"])
        parameters = json.loads(function["parameters"]) if function["parameters"] else []
        decorators = json.loads(function["decorators"]) if function["decorators"] else []

        p_slow = function.get("p_slow")
        try:
            p_slow = float(p_slow) if p_slow is not None else None
        except (TypeError, ValueError):
            p_slow = None

        all_functions_with_metrics[function["fqn"]] = {
            "parameters": parameters,
            "return_annotation": function["return_annotation"],
            "decorators": decorators,
            "docstring": function["docstring"],
            "static_features": {
                "cyclomatic_complexity": static_features["cyclomatic_complexity"],
                "cognitive_complexity": static_features["cognitive_complexity"],
                "loop_count": static_features["loop_count"],
            },
            "dynamic_features": {
                "inclusive_time_ms": round(function["inclusive_time_ms"], 2),
                "exclusive_time_ms": round(function["exclusive_time_ms"], 2),
                "call_count": function["call_count"],
                "fraction_of_total": round(function["fraction_of_total"], 2),
                "loop_iterations": function["loop_iterations_total"],
            },
            "ml_prediction": {
                "p_slow": p_slow,
            },
        }

    all_functions_text = format_functions_as_markdown(all_functions_with_metrics)

    # Assemble lines without any unintended indentation
    lines: List[str] = []
    lines.append(f"== Project Info for Project: {project_prefix} ==")
    lines.append(f"Total Project Runtime: {total_runtime:.2f}ms;")
    lines.append(f"Peak Memory Usage: {peak_memory_mb:.2f}MB;")
    lines.append(f"Total Number of Functions: {total_n_functions};")
    lines.append("")
    lines.append("All Functions with Statistics:")
    lines.append(all_functions_text)
    lines.append("")
    lines.append("Call Tree:")
    lines.append(call_tree_text if call_tree_text else "(no call tree)")
    lines.append("")
    lines.append("Hottest Execution Paths:")
    lines.append(hot_paths_text if hot_paths_text else "(no hot paths)")

    evidence_string = "\n".join(lines).rstrip()
    return evidence_string