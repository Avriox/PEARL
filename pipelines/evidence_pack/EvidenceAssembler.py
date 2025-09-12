import json
import logging
from pathlib import Path
from typing import List, Dict

from pipelines.code_analysis import Project, ChunkDatabase


def get_call_tree_from_edges(db: ChunkDatabase, project_id: str, run_id: str) -> Dict:
    """Build a call tree from dynamic edges, pruning by edge time and child inclusive time."""
    # Total runtime (for thresholding)
    total_rows = db.execute_sql(
        f"""
        SELECT total_time_ms
        FROM dynamic_runs
        WHERE project_id = '{project_id}' AND run_id = '{run_id}'
        LIMIT 1
        """
    )
    total_ms = float(total_rows) if total_rows else 0.0

    # Dynamic function metrics
    functions = db.execute_sql(
        f"""
        SELECT fqn, exclusive_time_ms, inclusive_time_ms, call_count, fraction_of_total
        FROM dynamic_functions
        WHERE project_id = '{project_id}' AND run_id = '{run_id}'
        """
    )
    if not functions:
        return None
    func_metrics = {f["fqn"]: f for f in functions}

    # Dynamic edges (with time)
    edges = db.execute_sql(
        f"""
        SELECT caller, callee, time_ms, count
        FROM dynamic_edges
        WHERE project_id = '{project_id}' AND run_id = '{run_id}'
        """
    )

    # Build adjacency with edge weights
    from collections import defaultdict

    children = defaultdict(list)  # caller -> [(callee, edge_ms)]
    all_callees = set()
    for e in edges:
        caller = e["caller"]
        callee = e["callee"]
        edge_ms = float(e.get("time_ms", 0.0) or 0.0)
        children[caller].append((callee, edge_ms))
        all_callees.add(callee)

    # Entry points = functions that are not called by any other function
    all_funcs = set(func_metrics.keys())
    entry_points = list(all_funcs - all_callees)

    # Fallback: pick top inclusive-time function if no clean entry point is found
    if not entry_points:
        entry_points = [
            max(all_funcs, key=lambda f: func_metrics[f]["inclusive_time_ms"])
        ]

    # Choose the main entry (highest inclusive time)
    main_entry = max(
        entry_points, key=lambda f: func_metrics.get(f, {}).get("inclusive_time_ms", 0)
    )

    # Thresholds for pruning
    edge_min_frac_total = 0.01  # keep child if edge contributes >=1% of total runtime
    child_incl_min_frac_total = 0.01  # or child’s inclusive time >=1% of total runtime
    max_children = 3
    max_depth = 4

    def build_subtree(fqn: str, visited: set, depth: int = 0) -> Dict:
        if depth >= max_depth or fqn in visited or fqn not in func_metrics:
            return None
        visited = set(visited)
        visited.add(fqn)

        m = func_metrics[fqn]

        # Consider children significant if edge time is big, or child’s inclusive time is big
        candidates = []
        for child_fqn, edge_ms in children.get(fqn, []):
            if child_fqn not in func_metrics:
                continue
            edge_frac = (edge_ms / total_ms) if total_ms > 0 else 0.0
            child_incl = float(func_metrics[child_fqn]["inclusive_time_ms"])
            child_incl_frac = (child_incl / total_ms) if total_ms > 0 else 0.0

            if (
                edge_frac >= edge_min_frac_total
                or child_incl_frac >= child_incl_min_frac_total
            ):
                child_tree = build_subtree(child_fqn, visited, depth + 1)
                if child_tree:
                    candidates.append((child_tree, edge_ms))

        # Sort children by edge time descending and keep top K
        candidates.sort(key=lambda t: t[1], reverse=True)
        child_trees = [t[0] for t in candidates[:max_children]]

        return {
            "name": fqn.split(".")[-1],
            "fqn": fqn,
            "exclusive_ms": m["exclusive_time_ms"],
            "inclusive_ms": m["inclusive_time_ms"],
            "fraction": m[
                "fraction_of_total"
            ],  # exclusive fraction; that’s fine for display
            "calls": m["call_count"],
            "children": child_trees,
        }

    return build_subtree(main_entry, set())


def format_tree_for_llm(tree: Dict, indent: int = 0) -> str:
    """Format call tree in a readable way for LLM"""
    if not tree:
        return ""

    lines = []
    prefix = "  " * indent

    # Indicators for significance
    # if tree["fraction"] > 0.10:
    #     indicator = "🔥"  # >10% of runtime
    # elif tree["fraction"] > 0.05:
    #     indicator = "⚠️"  # >5% of runtime
    # else:
    #     indicator = "→"

    indicator = "→"

    # Format: indicator name [exclusive/inclusive ms] (X% of total, N calls)
    line = f"{prefix}{indicator} {tree['name']} [{tree['exclusive_ms']:.1f}/{tree['inclusive_ms']:.1f}ms] ({tree['fraction']*100:.1f}%, {tree['calls']} calls)"
    lines.append(line)

    # Add children
    for child in tree.get("children", []):
        lines.append(format_tree_for_llm(child, indent + 1))

    return "\n".join(lines)


def get_hot_paths(
    db: ChunkDatabase, project_id: str, run_id: str, top_n: int = 5
) -> List[Dict]:
    """Get the hottest execution paths"""
    # Get top expensive functions
    bottlenecks = db.execute_sql(
        f"""
                                 SELECT fqn, exclusive_time_ms, fraction_of_total
                                 FROM dynamic_functions
                                 WHERE project_id = '{project_id}' AND run_id = '{run_id}'
                                 ORDER BY exclusive_time_ms DESC
                                 LIMIT {top_n*2}
                                 """
    )

    # Get edges to build paths
    edges = db.execute_sql(
        f"""
                           SELECT caller, callee
                           FROM dynamic_edges
                           WHERE project_id = '{project_id}' AND run_id = '{run_id}'
                           """
    )

    # Build parent map
    from collections import defaultdict

    parents = defaultdict(list)
    for edge in edges:
        parents[edge["callee"]].append(edge["caller"])

    hot_paths = []
    for bottleneck in bottlenecks[:top_n]:
        # Build path from entry to this bottleneck
        path = []
        current = bottleneck["fqn"]
        visited = set()

        while current and current not in visited:
            visited.add(current)
            path.append(current)
            # Get parent with highest inclusive time
            if current in parents:
                current = parents[current][0] if parents[current] else None
            else:
                current = None

        path.reverse()  # Start from entry point

        if len(path) > 1:  # Only include actual paths
            hot_paths.append(
                {
                    "path": path,
                    "bottleneck_ms": bottleneck["exclusive_time_ms"],
                    "bottleneck_fraction": bottleneck["fraction_of_total"],
                }
            )

    return hot_paths


def format_hot_paths_for_llm(hot_paths: List[Dict]) -> str:
    """Format hot paths for LLM understanding"""
    lines = []

    for i, path_info in enumerate(hot_paths, 1):
        path = path_info["path"]
        bottleneck_ms = path_info["bottleneck_ms"]
        bottleneck_frac = path_info["bottleneck_fraction"]

        lines.append(
            f"\nHot Path #{i} ({bottleneck_frac*100:.1f}% of runtime, {bottleneck_ms:.1f}ms)"
        )

        # Show call chain
        for j, fqn in enumerate(path):
            func_name = fqn.split(".")[-1]
            if j == len(path) - 1:
                lines.append(f"  \t └─> {func_name} ")  # ← BOTTLENECK
            else:
                lines.append(f"  → {func_name}")

    return "\n".join(lines)


def assemble_evidence_pack(project: Project, db_path: Path = Path("chunks.db")):
    logging.info(
        f'=== Assembling EvidencePack for Project: {project.config["project"]["name"]} ==='
    )

    db = ChunkDatabase(db_path)

    # Get the call tree

    latest_run = db.execute_sql(
        f"""SELECT run_id FROM dynamic_runs 
            WHERE project_id = '{project.config["project"]["id"]}' 
            ORDER BY timestamp DESC LIMIT 1"""
    )
    run_id = latest_run

    # Add call tree and hot paths to your existing evidence_string
    call_tree = get_call_tree_from_edges(db, project.config["project"]["id"], run_id)
    hot_paths = get_hot_paths(db, project.config["project"]["id"], run_id, top_n=1)

    # Get general metrics
    total_runtime = db.execute_sql(
        f"SELECT total_time_ms FROM dynamic_runs WHERE project_id = '{project.config["project"]["id"]}'"
    )
    # TODO they need version numbers!!
    total_n_functions = db.execute_sql(
        f"SELECT COUNT(*) FROM functions WHERE project_id = '{project.config["project"]["id"]}'"
    )

    # Get function specific metricd

    all_functions_with_metrics_raw = db.execute_sql(
        f"""SELECT 
            f.function_name, 
            f.parameters, 
            f.return_annotation, 
            f.decorators, 
            f.docstring, 
            f.static_features, 
            df.inclusive_time_ms, 
            df.exclusive_time_ms, 
            df.call_count, 
            df.fraction_of_total,
            df.loop_iterations_total
             FROM functions f
            JOIN dynamic_functions df ON f.fqn = df.fqn
            WHERE f.project_id ='{project.config["project"]["id"]}'"""
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

        all_functions_with_metrics[function["function_name"]] = {
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
        f"SELECT peak_memory_mb FROM dynamic_runs WHERE project_id ='{project.config["project"]["id"]}' AND run_id = '{run_id}'"
    )

    evidence_string = f"""
== Project Info for Project: {project.config["project"]["name"]} ==
Total Project Runtime: {total_runtime:.2f}ms;
Peak Memory Usage: {peak_memory_mb:.2f}MB;
Total Number of Functions: {total_n_functions};

All Functions with Statistics:
{json.dumps(all_functions_with_metrics, indent=2)} 
    
Call Tree: 
{format_tree_for_llm(call_tree)}

Hottest Execution Paths: 
{format_hot_paths_for_llm(hot_paths)}
    """

    print(evidence_string)
