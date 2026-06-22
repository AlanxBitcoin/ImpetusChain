import argparse
import sys
from pathlib import Path
from pprint import pprint

if __package__ in {None, ""}:
    src_root = Path(__file__).resolve().parents[1]
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))

from impetus_chain.pipeline import run_project_pipeline
from impetus_chain.project_service import create_project
from impetus_chain.ui_server import run_ui_server


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8088


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Financial impetus transmission chain CLI")
    subparsers = parser.add_subparsers(dest="command")

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

    ui_parser = subparsers.add_parser("ui", help="Start browser UI server.")
    ui_parser.add_argument("--host", type=str, default=DEFAULT_HOST, help="Bind host")
    ui_parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Bind port")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        run_ui_server(host=DEFAULT_HOST, port=DEFAULT_PORT)
        return

    if args.command == "init-project":
        try:
            saved_path, requirements_path, strategy_path, prompt_path = create_project(
                args.project, force=args.force
            )
        except (ValueError, FileExistsError) as exc:
            parser.error(str(exc))
        print(f"Project initialized: {saved_path.as_posix()}")
        print(f"Requirements template: {requirements_path.as_posix()}")
        print(f"Analysis strategy: {strategy_path.as_posix()}")
        print(f"AI prompt file: {prompt_path.as_posix()}")
        print("Next: manually edit the JSON data to refine tree nodes/weights.")
        return

    if args.command == "run":
        result = run_project_pipeline(args.project, shock=args.shock, source=args.source)
        pprint(result)
        return

    if args.command == "ui":
        run_ui_server(host=args.host, port=args.port)
        return

    parser.error("Unknown command")


if __name__ == "__main__":
    main()
