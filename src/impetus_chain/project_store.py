import json
from datetime import datetime, timezone
from pathlib import Path

from .models import Edge, Node

PROJECTS_DIR = Path("projects")


def project_data_dir(project: str) -> Path:
    return PROJECTS_DIR / project / "data"


def project_core_dir(project: str) -> Path:
    return PROJECTS_DIR / project / "core"


def project_chain_path(project: str) -> Path:
    return project_data_dir(project) / "chain.json"


def project_requirements_path(project: str) -> Path:
    return project_data_dir(project) / "requirements.md"


def project_strategy_path(project: str) -> Path:
    return project_core_dir(project) / "analysis_strategy.yaml"


def project_ai_prompt_path(project: str) -> Path:
    return project_core_dir(project) / "ai_prompt.md"


def project_analysis_dir(project: str) -> Path:
    return project_core_dir(project) / "analysis"


def project_analysis_status_path(project: str) -> Path:
    return project_analysis_dir(project) / "status.json"


def project_analysis_result_path(project: str, run_id: str, suffix: str = "md") -> Path:
    return project_analysis_dir(project) / f"{run_id}.{suffix}"


def ensure_project_dirs(project: str) -> tuple[Path, Path]:
    data_dir = project_data_dir(project)
    data_dir.mkdir(parents=True, exist_ok=True)
    core_dir = project_core_dir(project)
    core_dir.mkdir(parents=True, exist_ok=True)
    project_analysis_dir(project).mkdir(parents=True, exist_ok=True)
    return data_dir, core_dir


def save_chain_project(project: str, payload: dict) -> Path:
    ensure_project_dirs(project)
    chain_path = project_chain_path(project)
    chain_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return chain_path


def load_chain_project(project: str) -> dict:
    chain_path = project_chain_path(project)
    if not chain_path.exists():
        raise FileNotFoundError(
            f"Project '{project}' not found. Expected file: {chain_path.as_posix()}"
        )
    return json.loads(chain_path.read_text(encoding="utf-8"))


def write_requirements_template(project: str, force: bool = False) -> Path:
    ensure_project_dirs(project)
    req_path = project_requirements_path(project)
    if req_path.exists() and not force:
        return req_path

    template = f"""# Requirements - {project}

## 1. Business Scope
- Market universe:
- Instruments:
- Frequency:

## 2. Impetus Factor Library
- Macro factors:
- Micro factors:
- Event factors:

## 3. Transmission Tree Rules
- Root node:
- Layer definition:
- Weight range:
- Manual override policy:

## 4. Data Workflow
- AI-generated draft:
- Human review checklist:
- Versioning method:

## 5. Evaluation
- Signal metrics:
- Portfolio metrics:
- Risk constraints:

## 6. Open Questions
- Q1:
- Q2:
"""
    req_path.write_text(template, encoding="utf-8")
    return req_path


def write_strategy_template(project: str, force: bool = False) -> Path:
    ensure_project_dirs(project)
    strategy_path = project_strategy_path(project)
    if strategy_path.exists() and not force:
        return strategy_path

    template = """version: 1
task_id: node_speculation
objective: "Analyze speculative opportunity for a selected node."
output_requirements:
  - "Opportunity direction: long / short / neutral"
  - "3-5 logic chain bullets"
  - "Trigger conditions"
  - "Risk factors"
  - "Data to collect next"
scoring:
  horizon: "1-20 trading days"
  confidence_scale: "0-100"
  risk_reward_scale: "1-5"
constraints:
  - "State assumptions explicitly"
  - "Do not fabricate unavailable data"
"""
    strategy_path.write_text(template, encoding="utf-8")
    return strategy_path


def write_ai_prompt_template(project: str, force: bool = False) -> Path:
    ensure_project_dirs(project)
    prompt_path = project_ai_prompt_path(project)
    if prompt_path.exists() and not force:
        return prompt_path

    template = """# Role
You are a disciplined financial research assistant.

# Task
Analyze one selected node inside an impetus transmission tree and identify speculative opportunities.

# Response Format
1. Opportunity Direction
2. Logic Chain
3. Trigger Conditions
4. Risks
5. Missing Data

# Rules
- Keep statements evidence-oriented.
- Mark uncertainty clearly.
- Avoid investment guarantee language.
"""
    prompt_path.write_text(template, encoding="utf-8")
    return prompt_path


def read_text_file(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def save_analysis_status(project: str, status: dict) -> Path:
    ensure_project_dirs(project)
    path = project_analysis_status_path(project)
    path.write_text(json.dumps(status, indent=2), encoding="utf-8")
    return path


def load_analysis_status(project: str) -> dict:
    path = project_analysis_status_path(project)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_analysis_result(
    project: str,
    run_id: str,
    provider: str,
    node: str,
    analysis_text: str,
) -> Path:
    ensure_project_dirs(project)
    path = project_analysis_result_path(project, run_id, suffix="md")
    content = (
        f"# Node Analysis Result\n\n"
        f"- run_id: {run_id}\n"
        f"- provider: {provider}\n"
        f"- node: {node}\n"
        f"- generated_at_utc: {datetime.now(timezone.utc).isoformat()}\n\n"
        f"## Analysis\n\n{analysis_text.strip()}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def parse_nodes(payload: dict) -> list[Node]:
    nodes = payload.get("nodes", [])
    return [
        Node(
            name=node["name"],
            layer=node.get("layer", "unknown"),
            metadata=node.get("metadata", {}),
        )
        for node in nodes
    ]


def parse_edges(payload: dict) -> list[Edge]:
    edges = payload.get("edges", [])
    return [
        Edge(
            src=edge["src"],
            dst=edge["dst"],
            weight=float(edge["weight"]),
        )
        for edge in edges
    ]
