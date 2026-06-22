from dataclasses import dataclass


@dataclass(slots=True)
class ChainConfig:
    decay: float = 0.9
    max_hops: int = 3
    min_signal: float = 0.01

