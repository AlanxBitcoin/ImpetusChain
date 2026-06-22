import argparse
from pprint import pprint

from .ai_seed import build_ai_seed_project
from .pipeline import run_project_pipeline
from .project_store import (
    project_chain_path,
    save_chain_project,
    write_requirements_template,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Financial impetus transmission chain CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init-project", help="Create a new chain project with AI-generated draft data."
    )
    init_parser.add_argument("--project", required=True, help="Project name")
    init_parser.add_argument(
        "--force", action="store_true", help="Overwrite existing project chain data"
    )

    run_parser = subparsers.add_parser(
        "run", help="Run transmission propagation for a project."
    )
    run_parser.add_argument("--project", required=True, help="Project name")
    run_parser.add_argument("--shock", type=float, default=1.0, help="Input shock amplitude")
    run_parser.add_argument(
        "--source", type=str, default=None, help="Optional propagation source node"
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "init-project":
        output_path = project_chain_path(args.project)
        if output_path.exists() and not args.force:
            parser.error(
                f"Project already exists at {output_path.as_posix()}. "
                "Use --force to overwrite."
            )
        payload = build_ai_seed_project(args.project)
        saved_path = save_chain_project(args.project, payload)
        requirements_path = write_requirements_template(args.project, force=args.force)
        print(f"Project initialized: {saved_path.as_posix()}")
        print(f"Requirements template: {requirements_path.as_posix()}")
        print("Next: manually edit the JSON data to refine tree nodes/weights.")
        return

    if args.command == "run":
        result = run_project_pipeline(args.project, shock=args.shock, source=args.source)
        pprint(result)
        return

    parser.error("Unknown command")


if __name__ == "__main__":
    main()
