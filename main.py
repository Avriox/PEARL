from pathlib import Path

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
    ca_pipe.close()

    embedding_pipe = EmbeddingPipeline(db_path)

    projects = ca_pipe.get_projects()
    for project in projects:
        embedding_pipe.score_project(project)
    #     ea = assemble_evidence_pack(project, db_path)
    #
    #     print(ea)
    #
    #     llm = LLMClient(
    #         model="deepseek/deepseek-chat",
    #         db_path=db_path,
    #         project_id=project.project_info["id"],
    #         temperature=1.0
    #     )
    #
    #     llm.optimize(
    #         profiling_evidence=ea
    #     )

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
