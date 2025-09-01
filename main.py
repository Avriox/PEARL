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

    # Check project status
    print("\n=== Project Status ===")
    for status in ca_pipe.get_project_status():
        print(f"Project: {status['project_name']}")
        print(f"  - In DB: {status['in_database']}")
        print(f"  - Up to date: {status['up_to_date']}")
        print(f"  - Chunks: {status['chunks_count']}")
        print(f"  - Current hash: {status['current_hash']}")
        print(f"  - Stored hash: {status['stored_hash']}")
        print()

    ca_pipe.extract_code_chunks()
    ca_pipe.close()


if __name__ == "__main__":
    main()
