from pathlib import Path
from typing import List, Dict, Any

from pipelines import CodeAnalysisPipeline
import logging

from pipelines.LLM.llm import LLMClient
from pipelines.embedding.embeddingPipeline import EmbeddingPipeline
from pipelines.evidence_pack.EvidenceAssembler import assemble_evidence_pack



def main() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(message)s",
        style="%",
        datefmt="%Y-%m-%d %H:%M",
        level=logging.INFO,
    )

    db_path = Path("chunks.db")

    logging.info("=== Starting PEARL ===")
    ca_pipe = CodeAnalysisPipeline(db_path)
    ca_pipe.load_projects("./test-projects/")

    ca_pipe.extract_and_analyze()
    ca_pipe.run_dynamic_analysis()
    # ca_pipe.close()

    embedding_pipe = EmbeddingPipeline(db_path)

    projects = ca_pipe.get_projects()
    for project in projects:

        project_id = project.project_info["id"]

        def reprofile_and_refresh(bottlenecks: List[Dict[str, Any]], session_id: str, round_idx: int, model: str) -> Dict[str, Any]:
            # Apply patches + reprofile the single project
            run = ca_pipe.rerun_dynamic_analysis_for_project(
                project=project,
                bottlenecks=bottlenecks,
                session_id=session_id,
                llm_model=model,
                round_idx=round_idx,
                embedding_pipe=embedding_pipe,  # pass embedding pipeline so re-scoring happens post re-profile
            )
            if not run:
                # Failed (patch error or runtime crash). Return patched FQNs for logging.
                patched_fqns = [b.get("fqn") for b in bottlenecks if isinstance(b, dict) and (b.get("replacement_source") or "").strip().startswith("def ")]
                return {"ok": False, "error": "patched run failed", "patched_fqns": patched_fqns}

            # Build a fresh evidence pack using the latest DB state (dynamic + static + updated embedding predictions)
            new_evidence = assemble_evidence_pack(project, db_path)
            patched_fqns = [b.get("fqn") for b in bottlenecks if isinstance(b, dict)]
            return {
                "ok": True,
                "evidence": new_evidence,
                "run_id": run.run_id,
                "total_time_ms": run.total_time_ms,
                "patched_fqns": patched_fqns
            }

        # Baseline scoring before first evidence pack.
        print(embedding_pipe.score_project(project))
        ea = assemble_evidence_pack(project, db_path)

        print(ea)

        # llm = LLMClient(
        #     model="deepseek/deepseek-chat",
        #     db_path=db_path,
        #     project_id=project_id,
        #     temperature=1.0,
        #     reprofile_hook=reprofile_and_refresh,  # pass the hook here
        # )
        #
        # llm.optimize(
        #     profiling_evidence=ea
        # )

        # orch = PearlLLMOrchestrator(
        #     model=" deepseek/deepseek-chat",  # or openai/gpt-4o-mini, etc.
        #     db_path=db_path,
        #     project_id=project.project_info["id"],
        #     chuncks_db_path=db_path,
        # )
        #
        # results = orch.run_triage_and_inspection(
        #     evidence_pack=ea,
        #     # profiling_run_id=profiling_run_id,
        #     max_rounds=3,
        # )


if __name__ == "__main__":
    main()