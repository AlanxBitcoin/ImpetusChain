import json
from pathlib import Path

from .models import Edge, Node

PROJECTS_DIR = Path("projects")


def project_data_dir(project: str) -> Path:
    return PROJECTS_DIR / project / "data"


def project_chain_path(project: str) -> Path:
    return project_data_dir(project) / "chain.json"


def project_requirements_path(project: str) -> Path:
    return project_data_dir(project) / "requirements.md"


def ensure_project_dirs(project: str) -> Path:
    data_dir = project_data_dir(project)
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


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
