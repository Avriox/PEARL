from pathlib import Path
from typing import Dict, List, Any, Optional

from .llm_client import LLMClient
from .schemas import TriageReply, InspectionReply
from .prompts import SYSTEM_PROMPT, triage_user_prompt, inspection_user_prompt
from .llm_db import LLMDatabase
from ..code_analysis import ChunkDatabase


class PearlLLMOrchestrator:
    """
    Minimal triage/inspection loop with full DB logging.

    You provide:
      - model: LiteLLM model string (e.g., "openai/gpt-4o-mini", "anthropic/claude-3-5-sonnet-20240620", etc.)
      - db_path: path to the existing SQLite database file (shared with your ChunkDatabase)
      - project_id: current project identifier (matches your DB)
      - chuncks_db_path: path to the same SQLite; used to fetch function sources

    You call:
      - run_triage_and_inspection(evidence_pack: str, profiling_run_id: Optional[str] = None, max_rounds: int = 2)

    Returns:
      - dict with keys: model, triage_status, hypotheses (list), bottlenecks (list), llm_run_id
    """

    def __init__(
        self,
        model: str,
        db_path: Path,
        project_id: str,
        chuncks_db_path: str,
        temperature: float = 0.2,
    ):
        # Normalize model string to avoid leading/trailing whitespace
        self.model = (model or "").strip()
        self.project_id = project_id

        self.client = LLMClient(model=self.model, temperature=temperature)

        self.chunks_db = ChunkDatabase(Path(chuncks_db_path))
        self.db = LLMDatabase(db_path=Path(db_path))

    def get_code_for_fqn(self, fqn: str) -> str:
        # Returns a single value from your execute_sql helper
        return self.chunks_db.execute_sql(
            f"SELECT source_code FROM functions WHERE fqn = '{fqn}' AND project_id = '{self.project_id}'"
        )

    def run_triage_and_inspection(
        self,
        evidence_pack: str,
        profiling_run_id: Optional[str] = None,
        max_rounds: int = 2,
    ) -> Dict[str, Any]:
        # Begin a new LLM run and log the system + triage user prompts
        llm_run_id = self.db.begin_run(
            project_id=self.project_id,
            model=self.model,
            system_prompt=SYSTEM_PROMPT,
            profiling_run_id=profiling_run_id,
        )

        messages: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        # iteration 0: triage stage
        self.db.log_message(
            llm_run_id,
            iteration=0,
            stage="triage",
            role="system",
            content=SYSTEM_PROMPT,
        )

        triage_user = triage_user_prompt(evidence_pack)
        messages.append({"role": "user", "content": triage_user})
        self.db.log_message(
            llm_run_id, iteration=0, stage="triage", role="user", content=triage_user
        )

        triage: TriageReply = self.client.structured_chat(messages, TriageReply)
        triage_json = triage.model_dump_json()
        self.db.log_message(
            llm_run_id,
            iteration=0,
            stage="triage",
            role="assistant",
            content=triage_json,
        )
        self.db.log_code_requests(
            llm_run_id, iteration=0, requests=triage.code_requests
        )
        self.db.log_hypotheses(llm_run_id, iteration=0, hypos=triage.hypotheses)

        results: Dict[str, Any] = {
            "llm_run_id": llm_run_id,
            "model": self.model,
            "triage_status": triage.status,
            "hypotheses": [h.model_dump() for h in triage.hypotheses],
            "bottlenecks": [],
        }

        if triage.status == "done" and not triage.code_requests:
            self.db.end_run(llm_run_id, status="done")
            return results

        # Rounds 1..N: inspection with targeted code
        rounds = 0
        pending_requests = triage.code_requests

        while pending_requests and rounds < max_rounds:
            iteration = rounds + 1  # triage=0, first inspection=1
            code_bundle: Dict[str, str] = {}
            for req in pending_requests:
                if req.type == "function_source":
                    code_bundle[req.fqn] = self.get_code_for_fqn(req.fqn)

            # Keep prior structured reply in the conversation
            messages.append({"role": "assistant", "content": triage_json})
            # Provide code for requested functions
            inspection_user = inspection_user_prompt(evidence_pack, code_bundle)
            messages.append({"role": "user", "content": inspection_user})

            # Log user message for inspection stage
            self.db.log_message(
                llm_run_id,
                iteration=iteration,
                stage="inspection",
                role="user",
                content=inspection_user,
            )

            inspection: InspectionReply = self.client.structured_chat(
                messages, InspectionReply
            )
            inspection_json = inspection.model_dump_json()
            self.db.log_message(
                llm_run_id,
                iteration=iteration,
                stage="inspection",
                role="assistant",
                content=inspection_json,
            )

            # Log new code requests (if any) and findings
            self.db.log_code_requests(
                llm_run_id, iteration=iteration, requests=inspection.code_requests
            )
            self.db.log_findings(
                llm_run_id,
                iteration=iteration,
                project_id=self.project_id,
                findings=inspection.bottlenecks,
            )

            results["bottlenecks"].extend(
                b.model_dump() for b in inspection.bottlenecks
            )

            if inspection.status == "done":
                self.db.end_run(llm_run_id, status="done")
                break

            pending_requests = inspection.code_requests
            rounds += 1

        if rounds >= max_rounds and pending_requests:
            # Ended due to iteration budget
            self.db.end_run(llm_run_id, status="stopped_max_rounds")
        elif not pending_requests:
            # No more requests, but model didn't explicitly say done (be conservative)
            self.db.end_run(llm_run_id, status="completed_no_requests")

        return results
