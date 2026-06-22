from pathlib import Path

from .ai_seed import build_ai_seed_project
from .project_store import (
    project_chain_path,
    save_chain_project,
    write_ai_prompt_template,
    write_requirements_template,
    write_strategy_template,
)


def validate_project_name(project: str) -> str:
    project = project.strip()
    if not project:
        raise ValueError("Project name cannot be empty.")
    if project in {".", ".."}:
        raise ValueError("Project name is invalid.")
    if any(ch in project for ch in ("/", "\\", ":", "*", "?", '"', "<", ">", "|")):
        raise ValueError("Project name contains invalid path characters.")
    return project


def create_project(project: str, force: bool = False) -> tuple[Path, Path, Path, Path]:
    safe_project = validate_project_name(project)
    output_path = project_chain_path(safe_project)
    if output_path.exists() and not force:
        raise FileExistsError(
            f"Project already exists at {output_path.as_posix()}. Use force to overwrite."
        )
    payload = build_ai_seed_project(safe_project, root=safe_project)
    saved_path = save_chain_project(safe_project, payload)
    requirements_path = write_requirements_template(safe_project, force=force)
    strategy_path = write_strategy_template(safe_project, force=force)
    prompt_path = write_ai_prompt_template(safe_project, force=force)
    return saved_path, requirements_path, strategy_path, prompt_path
