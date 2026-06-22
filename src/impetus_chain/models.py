from dataclasses import dataclass, field


@dataclass(slots=True)
class Node:
    name: str
    layer: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class Edge:
    src: str
    dst: str
    weight: float

