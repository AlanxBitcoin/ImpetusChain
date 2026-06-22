from collections import defaultdict

from .config import ChainConfig
from .models import Edge


class TransmissionChain:
    def __init__(self, edges: list[Edge], config: ChainConfig | None = None) -> None:
        self.config = config or ChainConfig()
        self.graph: dict[str, list[tuple[str, float]]] = defaultdict(list)
        for edge in edges:
            self.graph[edge.src].append((edge.dst, edge.weight))

    def propagate(self, source: str, shock: float) -> dict[str, float]:
        scores: dict[str, float] = defaultdict(float)
        frontier: list[tuple[str, float, int]] = [(source, shock, 0)]

        while frontier:
            node, signal, hop = frontier.pop(0)
            if abs(signal) < self.config.min_signal:
                continue

            scores[node] += signal
            if hop >= self.config.max_hops:
                continue

            for dst, weight in self.graph.get(node, []):
                next_signal = signal * weight * self.config.decay
                frontier.append((dst, next_signal, hop + 1))

        return dict(scores)


def validate_tree(edges: list[Edge], root: str) -> None:
    parents: dict[str, str] = {}
    children: dict[str, list[str]] = defaultdict(list)
    nodes: set[str] = {root}

    for edge in edges:
        nodes.add(edge.src)
        nodes.add(edge.dst)
        children[edge.src].append(edge.dst)
        if edge.dst in parents:
            raise ValueError(f"Node '{edge.dst}' has multiple parents; not a tree.")
        parents[edge.dst] = edge.src

    for node in nodes:
        if node == root:
            if node in parents:
                raise ValueError("Root node cannot have a parent.")
            continue
        if node not in parents:
            raise ValueError(f"Node '{node}' is disconnected from root '{root}'.")

    visited: set[str] = set()
    stack: set[str] = set()

    def dfs(node: str) -> None:
        if node in stack:
            raise ValueError(f"Cycle detected at node '{node}'; not a tree.")
        if node in visited:
            return
        stack.add(node)
        for child in children.get(node, []):
            dfs(child)
        stack.remove(node)
        visited.add(node)

    dfs(root)
    if visited != nodes:
        missing = ", ".join(sorted(nodes - visited))
        raise ValueError(f"Unreachable nodes from root '{root}': {missing}")
