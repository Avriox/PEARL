import sqlite3
import uuid
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

from .schemas import FunctionCodeRequest, BottleneckHypothesis, BottleneckFinding


class LLMDatabase:
    """
    Lightweight logger that shares the same SQLite file as your main project DB.
    Creates separate llm_* tables and indexes (non-invasive).
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._create_llm_tables()

    def _create_llm_tables(self):
        cur = self.conn.cursor()
        # Main run/session
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_runs (
                llm_run_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                profiling_run_id TEXT,
                model TEXT NOT NULL,
                system_prompt TEXT,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                status TEXT
            )
            """
        )
        # Messages exchanged
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                llm_run_id TEXT NOT NULL,
                iteration INTEGER NOT NULL,
                stage TEXT NOT NULL, -- 'triage' or 'inspection'
                role TEXT NOT NULL,  -- 'system' | 'user' | 'assistant'
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (llm_run_id) REFERENCES llm_runs(llm_run_id)
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_llm_messages_run ON llm_messages(llm_run_id)"
        )

        # Code requests
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_code_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                llm_run_id TEXT NOT NULL,
                iteration INTEGER NOT NULL,
                fqn TEXT NOT NULL,
                reason TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (llm_run_id) REFERENCES llm_runs(llm_run_id)
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_llm_codereq_run ON llm_code_requests(llm_run_id)"
        )

        # Hypotheses (from triage stage)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_hypotheses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                llm_run_id TEXT NOT NULL,
                iteration INTEGER NOT NULL,
                fqn TEXT NOT NULL,
                bottleneck_type TEXT NOT NULL,
                confidence REAL NOT NULL,
                issue_description TEXT NOT NULL,
                estimated_impact_percent REAL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (llm_run_id) REFERENCES llm_runs(llm_run_id)
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_llm_hyp_run ON llm_hypotheses(llm_run_id)"
        )

        # Findings (finalized after code inspection)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                llm_run_id TEXT NOT NULL,
                iteration INTEGER NOT NULL,
                fqn TEXT NOT NULL,
                bottleneck_type TEXT NOT NULL,
                confidence REAL NOT NULL,
                issue_description TEXT NOT NULL,
                suggested_fix_summary TEXT NOT NULL,
                estimated_impact_percent REAL NOT NULL,
                function_source_snapshot TEXT, -- full function text at time of finding
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (llm_run_id) REFERENCES llm_runs(llm_run_id)
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_llm_find_run ON llm_findings(llm_run_id)"
        )

        self.conn.commit()

    # --- Run lifecycle -------------------------------------------------------

    def begin_run(
        self,
        project_id: str,
        model: str,
        system_prompt: str,
        profiling_run_id: Optional[str] = None,
    ) -> str:
        run_id = str(uuid.uuid4())
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO llm_runs (llm_run_id, project_id, profiling_run_id, model, system_prompt, started_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                project_id,
                profiling_run_id,
                model,
                system_prompt,
                datetime.utcnow().isoformat(),
                "running",
            ),
        )
        self.conn.commit()
        return run_id

    def end_run(self, llm_run_id: str, status: str):
        cur = self.conn.cursor()
        cur.execute(
            """
            UPDATE llm_runs
            SET status = ?, ended_at = ?
            WHERE llm_run_id = ?
            """,
            (status, datetime.utcnow().isoformat(), llm_run_id),
        )
        self.conn.commit()

    # --- Messaging -----------------------------------------------------------

    def log_message(
        self, llm_run_id: str, iteration: int, stage: str, role: str, content: str
    ):
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO llm_messages (llm_run_id, iteration, stage, role, content)
            VALUES (?, ?, ?, ?, ?)
            """,
            (llm_run_id, iteration, stage, role, content),
        )
        self.conn.commit()

    def log_code_requests(self, llm_run_id: str, iteration: int, requests: List[Dict]):
        if not requests:
            return
        cur = self.conn.cursor()
        rows = [(llm_run_id, iteration, r.fqn, r.reason) for r in requests]
        cur.executemany(
            """
            INSERT INTO llm_code_requests (llm_run_id, iteration, fqn, reason)
            VALUES (?, ?, ?, ?)
            """,
            rows,
        )
        self.conn.commit()

    def log_hypotheses(self, llm_run_id: str, iteration: int, hypos: List[Dict]):
        if not hypos:
            return
        cur = self.conn.cursor()
        rows = [
            (
                llm_run_id,
                iteration,
                h.fqn,
                h.bottleneck_type,
                float(h.confidence),
                h.issue_description,
                (
                    None
                    if h.estimated_impact_percent is None
                    else float(h.estimated_impact_percent)
                ),
            )
            for h in hypos
        ]
        cur.executemany(
            """
            INSERT INTO llm_hypotheses (llm_run_id, iteration, fqn, bottleneck_type, confidence, issue_description, estimated_impact_percent)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self.conn.commit()

    def log_findings(
        self, llm_run_id: str, iteration: int, project_id: str, findings: List[Dict]
    ):
        if not findings:
            return
        cur = self.conn.cursor()
        rows = []
        for f in findings:
            src = self._get_latest_function_source(project_id, f.fqn)
            rows.append(
                (
                    llm_run_id,
                    iteration,
                    f.fqn,
                    f.bottleneck_type,
                    float(f.confidence),
                    f.issue_description,
                    f.suggested_fix_summary,
                    float(f.estimated_impact_percent),
                    src,
                )
            )
        cur.executemany(
            """
            INSERT INTO llm_findings (
                llm_run_id, iteration, fqn, bottleneck_type, confidence, issue_description,
                suggested_fix_summary, estimated_impact_percent, function_source_snapshot
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self.conn.commit()

    # --- Helper: pull full function text snapshot ---------------------------

    def _get_latest_function_source(self, project_id: str, fqn: str) -> Optional[str]:
        """
        Snapshot the entire function text from your existing 'functions' table.
        """
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT source_code
            FROM functions
            WHERE project_id = ? AND fqn = ?
            ORDER BY version DESC
            LIMIT 1
            """,
            (project_id, fqn),
        )
        row = cur.fetchone()
        return row["source_code"] if row else None

    def close(self):
        self.conn.close()
