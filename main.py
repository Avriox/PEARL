from pipelines import CodeAnalysisPipeline
import logging


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(message)s",
        style="%",
        datefmt="%Y-%m-%d %H:%M",
        level=logging.DEBUG,
    )
    logging.info("=== Starting PEARL ===")
    ca_pipe = CodeAnalysisPipeline()
    ca_pipe.load_projects("./test-projects/")

    ca_pipe.extract_and_analyze()
    ca_pipe.run_dynamic_analysis()
    ca_pipe.close()


if __name__ == "__main__":
    main()
