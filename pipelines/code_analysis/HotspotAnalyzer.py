import logging
from typing import List, Dict, Any

from .ChunkDatabase import ChunkDatabase


class HotspotAnalyzer:
    """Post-profiling analysis: compute and store hotspots from dynamic_functions."""

    def __init__(self, db: ChunkDatabase):
        self.db = db

    def compute_hotspots(self, project_id: str, run_id: str, top_n: int = 50):
        rows = self.db.fetch_dynamic_functions(project_id, run_id)
        if not rows:
            logging.warning(f"No dynamic function metrics found for run {run_id}")
            return

        # Sort by exclusive time desc
        rows_sorted = sorted(
            rows, key=lambda r: r.get("exclusive_time_ms", 0.0) or 0.0, reverse=True
        )
        top = rows_sorted[:top_n]

        hotspots = []
        for r in top:
            hotspots.append(
                {
                    "fqn": r["fqn"],
                    "exclusive_time_ms": float(r.get("exclusive_time_ms", 0.0) or 0.0),
                    "fraction_of_total": float(r.get("fraction_of_total", 0.0) or 0.0),
                    "call_count": int(r.get("call_count", 0) or 0),
                    "avg_time_ms": float(r.get("avg_time_ms", 0.0) or 0.0),
                }
            )

        # Store
        self.db.clear_dynamic_hotspots(project_id, run_id)
        self.db.insert_dynamic_hotspots(project_id, run_id, hotspots)
