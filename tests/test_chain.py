from pathlib import Path

import pytest

from impetus_chain.chain import TransmissionChain
from impetus_chain.chain import validate_tree
from impetus_chain.models import Edge
from impetus_chain.pipeline import run_project_pipeline
from impetus_chain.project_store import save_chain_project


def test_propagation_reaches_downstream_nodes() -> None:
    chain = TransmissionChain(
        [
            Edge("a", "b", 0.5),
            Edge("b", "c", 0.5),
        ]
    )

    scores = chain.propagate("a", 1.0)
    assert "a" in scores
    assert "b" in scores
    assert "c" in scores
    assert scores["a"] > scores["b"] > scores["c"]


def test_validate_tree_rejects_multi_parent() -> None:
    edges = [
        Edge("root", "x", 0.5),
        Edge("root", "y", 0.5),
        Edge("y", "x", 0.3),
    ]
    with pytest.raises(ValueError):
        validate_tree(edges, root="root")


def test_run_project_pipeline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    payload = {
        "project": "demo",
        "root": "root",
        "nodes": [
            {"name": "root", "layer": "macro"},
            {"name": "child", "layer": "style"},
        ],
        "edges": [
            {"src": "root", "dst": "child", "weight": 0.5},
        ],
    }
    save_chain_project("demo", payload)
    scores = run_project_pipeline("demo", shock=1.0)
    assert scores["root"] > scores["child"] > 0
