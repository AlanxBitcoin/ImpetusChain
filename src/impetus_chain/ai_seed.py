from datetime import datetime, timezone


def build_ai_seed_project(project: str, root: str = "macro_impetus") -> dict:
    # Placeholder "AI + code" starter: produces an editable draft tree.
    nodes = [
        {"name": root, "layer": "macro", "metadata": {"role": "root"}},
        {"name": "liquidity", "layer": "macro"},
        {"name": "risk_sentiment", "layer": "macro"},
        {"name": "growth_style", "layer": "style"},
        {"name": "value_style", "layer": "style"},
        {"name": "tech_equity", "layer": "asset"},
        {"name": "bank_equity", "layer": "asset"},
    ]
    edges = [
        {"src": root, "dst": "liquidity", "weight": 0.9},
        {"src": root, "dst": "risk_sentiment", "weight": 0.7},
        {"src": "liquidity", "dst": "growth_style", "weight": 0.8},
        {"src": "risk_sentiment", "dst": "value_style", "weight": -0.4},
        {"src": "growth_style", "dst": "tech_equity", "weight": 0.7},
        {"src": "value_style", "dst": "bank_equity", "weight": 0.6},
    ]

    return {
        "project": project,
        "schema_version": "1.0",
        "root": root,
        "generated": {
            "by": "ai_seed_template",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "human_reviewed": False,
        },
        "notes": "AI generated draft. Human analysts should adjust nodes/edges/weights.",
        "nodes": nodes,
        "edges": edges,
    }
