import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import List, Dict, Tuple, Optional

from pipelines.code_analysis import Project, ChunkDatabase


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


def get_full_project_call_forest(
    db: ChunkDatabase,
    project_id: str,
    run_id: str,
    project_prefix: Optional[str] = None,
    include_external: bool = False,  # keep False to show only your package
    max_roots: int = 50,  # just a safety; set high, forest is otherwise “full”
    max_depth: Optional[int] = None,  # None == unlimited
) -> List[Dict]:
    """
    Build a full execution forest from dynamic edges:
      - Roots are in-project functions called from outside the project (best signal of entry).
        If none, fall back to in-project nodes with no in-project parents.
      - Only includes nodes reachable from these roots.
      - Filters noise endpoints like [self], <built-in>, <frozen ...>.
      - Each node: {fqn, exclusive_ms, inclusive_ms, fraction, calls, children[, recursion]}.
    """
    project_prefix = project_prefix or project_id
    in_pkg = lambda f: f.startswith(project_prefix + ".")

    # Load metrics
    rows = db.execute_sql(
        f"""
        SELECT fqn, exclusive_time_ms, inclusive_time_ms, call_count, fraction_of_total
        FROM dynamic_functions
        WHERE project_id = '{project_id}' AND run_id = '{run_id}'
    """
    )
    if not rows:
        return []
    func = {r["fqn"]: r for r in rows}

    # Load edges
    raw_edges = db.execute_sql(
        f"""
        SELECT caller, callee, time_ms, count
        FROM dynamic_edges
        WHERE project_id = '{project_id}' AND run_id = '{run_id}'
    """
    )

    # Filter and build adjacency
    children = defaultdict(list)  # parent -> [(child, edge_ms, count)]
    parents = defaultdict(list)  # child  -> [parent]
    nodes = set(func.keys())

    for e in raw_edges:
        a, b = e["caller"], e["callee"]
        if _is_noise_fqn(a) or _is_noise_fqn(b):
            continue
        if a not in func or b not in func:
            continue

        if not include_external:
            if not (in_pkg(a) and in_pkg(b)):
                continue

        w = float(e.get("time_ms", 0.0) or 0.0)
        c = int(e.get("count", 0) or 0)
        children[a].append((b, w, c))
        parents[b].append(a)

    # Entry root choice:
    # Preferred: in-project callees that were called from outside project.
    called_from_outside = set()
    if not include_external:
        for e in raw_edges:
            a, b = e["caller"], e["callee"]
            if _is_noise_fqn(a) or _is_noise_fqn(b):
                continue
            if b in func and in_pkg(b) and (a not in func or not in_pkg(a)):
                called_from_outside.add(b)

    roots = [n for n in called_from_outside if n in func]
    # Fallback: in-project nodes with no in-project parents
    if not roots:
        in_pkg_nodes = {n for n in nodes if in_pkg(n)}
        roots = [
            n for n in in_pkg_nodes if not any(in_pkg(p) for p in parents.get(n, []))
        ]

    # Last fallback: hottest in-project nodes
    if not roots:
        in_pkg_nodes = [n for n in nodes if in_pkg(n)]
        roots = sorted(
            in_pkg_nodes, key=lambda n: func[n]["inclusive_time_ms"], reverse=True
        )[:max_roots]

    # Sort children deterministically (edge time desc, then child inclusive desc)
    for p in children:
        children[p].sort(
            key=lambda t: (t[1], func[t[0]]["inclusive_time_ms"]), reverse=True
        )

    # Limit forest to nodes reachable from selected roots
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
            if max_depth is not None and depth > max_depth:
                return {
                    "fqn": u,
                    "exclusive_ms": float(func[u]["exclusive_time_ms"]),
                    "inclusive_ms": float(func[u]["inclusive_time_ms"]),
                    "fraction": float(func[u]["fraction_of_total"]),
                    "calls": int(func[u]["call_count"]),
                    "children": [],
                }
            if u in onstack:  # recursion
                return {
                    "fqn": u,
                    "exclusive_ms": float(func[u]["exclusive_time_ms"]),
                    "inclusive_ms": float(func[u]["inclusive_time_ms"]),
                    "fraction": float(func[u]["fraction_of_total"]),
                    "calls": int(func[u]["call_count"]),
                    "children": [],
                    "recursion": True,
                }
            onstack = set(onstack)
            onstack.add(u)
            node = {
                "fqn": u,
                "exclusive_ms": float(func[u]["exclusive_time_ms"]),
                "inclusive_ms": float(func[u]["inclusive_time_ms"]),
                "fraction": float(func[u]["fraction_of_total"]),
                "calls": int(func[u]["call_count"]),
                "children": [],
            }
            for v, _, _ in children.get(u, []):
                if v in reachable:
                    node["children"].append(dfs(v, onstack, depth + 1))
            return node

        return dfs(root, set(), 0)

    forest = [build_tree(r) for r in roots]
    return forest


def format_full_forest(forest: List[Dict], indent: int = 0) -> str:
    """
    Print each node as its FQN to keep identity crystal clear.
    """
    if not forest:
        return ""

    lines: List[str] = []

    def fmt(node: Dict, depth: int):
        fqn = node["fqn"]
        excl = node["exclusive_ms"]
        incl = node["inclusive_ms"]
        frac = node["fraction"]
        calls = node["calls"]
        rec = node.get("recursion", False)
        prefix = "  " * depth
        suffix = " ↻" if rec else ""
        lines.append(
            f"{prefix}→ {fqn} [{excl:.1f}/{incl:.1f}ms] ({frac*100:.1f}%, {calls} calls){suffix}"
        )
        if not rec:
            for ch in node.get("children", []):
                fmt(ch, depth + 1)

    for tree in forest:
        fmt(tree, indent)
        lines.append("")  # blank line between roots

    return "\n".join(lines).rstrip()


def get_hot_paths(
    db: ChunkDatabase,
    project_id: str,
    run_id: str,
    top_n: int = 5,
    project_prefix: str | None = None,
) -> List[Dict]:
    project_prefix = project_prefix or project_id

    bottlenecks = db.execute_sql(
        f"""
        SELECT fqn, exclusive_time_ms, fraction_of_total
        FROM dynamic_functions
        WHERE project_id = '{project_id}' AND run_id = '{run_id}'
        ORDER BY exclusive_time_ms DESC
        LIMIT {top_n*3}
    """
    )

    edges = db.execute_sql(
        f"""
        SELECT caller, callee, time_ms
        FROM dynamic_edges
        WHERE project_id = '{project_id}' AND run_id = '{run_id}'
    """
    )

    parents = defaultdict(list)
    for e in edges:
        c, d = e["caller"], e["callee"]
        if _is_noise_fqn(c) or _is_noise_fqn(d):
            continue
        parents[d].append((c, float(e.get("time_ms", 0.0) or 0.0)))

    hot_paths = []
    for b in bottlenecks:
        fqn = b["fqn"]
        if _is_noise_fqn(fqn):
            continue

        # Walk up picking the strongest incoming edge each step
        path = [fqn]
        seen = set(path)
        cur = fqn
        while cur in parents and parents[cur]:
            # prefer parents inside project
            in_pkg = [
                (p, w) for (p, w) in parents[cur] if p.startswith(project_prefix + ".")
            ]
            plist = in_pkg if in_pkg else parents[cur]
            p = max(plist, key=lambda t: t[1])[0]
            if p in seen:
                break
            path.append(p)
            seen.add(p)
            cur = p

        path.reverse()
        if len(path) > 1:
            hot_paths.append(
                {
                    "path": path,
                    "bottleneck_ms": float(b["exclusive_time_ms"]),
                    "bottleneck_fraction": float(b["fraction_of_total"]),
                }
            )
        if len(hot_paths) >= top_n:
            break

    return hot_paths


def format_hot_paths_for_llm(hot_paths: List[Dict], project_prefix: str) -> str:
    lines = []
    for i, info in enumerate(hot_paths, 1):
        path = info["path"]
        lines.append(
            f"\nHot Path #{i} ({info['bottleneck_fraction']*100:.1f}% of runtime, {info['bottleneck_ms']:.1f}ms)"
        )
        for j, fqn in enumerate(path):
            parent = path[j - 1] if j > 0 else None
            label = _edge_label(parent or "", fqn, project_prefix)
            if j == len(path) - 1:
                lines.append(f"  \t └─> {label}")
            else:
                lines.append(f"  → {label}")
    return "\n".join(lines)


def assemble_evidence_pack(project: Project, db_path: Path = Path("chunks.db")):
    logging.info(
        f'=== Assembling EvidencePack for Project: {project.config["project"]["id"]} ==='
    )
    db = ChunkDatabase(db_path)

    # latest run id
    run_id = db.execute_sql(
        f"""
        SELECT run_id
        FROM dynamic_runs
        WHERE project_id = '{project.config["project"]["id"]}'
        ORDER BY timestamp DESC LIMIT 1
    """
    )
    if not run_id:
        return "No runs found."

    project_prefix = project.config["project"]["id"]

    forest = get_full_project_call_forest(
        db,
        project_id=project_prefix,
        run_id=run_id,
        project_prefix=project_prefix,
        include_external=False,  # only your package
        max_roots=50,  # large but finite
        max_depth=None,  # unlimited
    )

    call_tree_text = format_full_forest(forest)

    # Hottest paths (optional, unchanged or adopt the same filtering)
    hot_paths = get_hot_paths(
        db, project_prefix, run_id, top_n=3, project_prefix=project_prefix
    )
    hot_paths_text = format_hot_paths_for_llm(hot_paths, project_prefix)

    # Totals
    row = db.execute_sql(
        f"""
        SELECT total_time_ms, peak_memory_mb
        FROM dynamic_runs
        WHERE project_id = '{project_prefix}' AND run_id = '{run_id}'
    """
    )
    total_runtime = float(row["total_time_ms"]) if row else 0.0
    peak_memory_mb = float(row["peak_memory_mb"]) if row else 0.0

    count = db.execute_sql(
        f"SELECT COUNT(*) AS n FROM functions WHERE project_id = '{project_prefix}'"
    )
    total_n_functions = count if count else 0

    # Function stats (your existing join)
    all_functions_with_metrics_raw = db.execute_sql(
        f"""
        SELECT 
            f.function_name, f.fqn, f.parameters, f.return_annotation, f.decorators, f.docstring, f.static_features,
            df.inclusive_time_ms, df.exclusive_time_ms, df.call_count, df.fraction_of_total, df.loop_iterations_total
        FROM functions f
        JOIN dynamic_functions df ON f.fqn = df.fqn
        WHERE f.project_id = '{project_prefix}' AND df.run_id = '{run_id}'
    """
    )

    all_functions_with_metrics = {}
    for function in all_functions_with_metrics_raw:
        static_features = json.loads(function["static_features"])

        # Parse the JSON strings into actual Python objects
        parameters = (
            json.loads(function["parameters"]) if function["parameters"] else []
        )
        decorators = (
            json.loads(function["decorators"]) if function["decorators"] else []
        )

        all_functions_with_metrics[function["fqn"]] = {
            "parameters": parameters,  # Now a list instead of a JSON string
            "return_annotation": function["return_annotation"],
            "decorators": decorators,  # Now a list instead of a JSON string
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
        }

    peak_memory_mb = db.execute_sql(
        f"SELECT peak_memory_mb FROM dynamic_runs WHERE project_id ='{project.config['project']['id']}' AND run_id = '{run_id}'"
    )

    evidence_string = f"""
    == Project Info for Project: {project_prefix} ==
    Total Project Runtime: {total_runtime:.2f}ms;
    Peak Memory Usage: {peak_memory_mb:.2f}MB;
    Total Number of Functions: {total_n_functions};

    All Functions with Statistics:
    {json.dumps(all_functions_with_metrics, indent=2)} 

    Call Tree:
    {call_tree_text}

    Hottest Execution Paths:
    {hot_paths_text}
        """
    return evidence_string
