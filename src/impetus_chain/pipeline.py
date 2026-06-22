from .chain import TransmissionChain, validate_tree
from .project_store import load_chain_project, parse_edges


def run_project_pipeline(
    project: str, shock: float = 1.0, source: str | None = None
) -> dict[str, float]:
    payload = load_chain_project(project)
    root = payload["root"]
    edges = parse_edges(payload)

    validate_tree(edges, root=root)
    chain = TransmissionChain(edges)
    return chain.propagate(source or root, shock)
