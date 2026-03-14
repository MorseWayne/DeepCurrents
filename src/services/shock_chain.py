from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger


# ── Shock-Chain: Causal propagation scaffold ──


@dataclass
class ShockNode:
    label: str
    node_type: (
        str  # "shock_source" | "macro_variable" | "market_pricing" | "allocation"
    )
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ShockEdge:
    source: str
    target: str
    mechanism: str = ""
    strength: float = 0.0  # 0..1
    lag_hours: float = 0.0


class ShockChain:
    def __init__(self) -> None:
        self._nodes: dict[str, ShockNode] = {}
        self._edges: list[ShockEdge] = []

    def add_node(self, node: ShockNode) -> None:
        self._nodes[node.label] = node

    def add_edge(self, edge: ShockEdge) -> None:
        if edge.source not in self._nodes:
            logger.warning(f"ShockChain: source node '{edge.source}' not found")
            return
        if edge.target not in self._nodes:
            logger.warning(f"ShockChain: target node '{edge.target}' not found")
            return
        self._edges.append(edge)

    def propagate(
        self, shock_source: str, initial_magnitude: float = 1.0
    ) -> dict[str, float]:
        if shock_source not in self._nodes:
            return {}

        impacts: dict[str, float] = {shock_source: initial_magnitude}
        visited: set[str] = set()
        frontier = [shock_source]

        while frontier:
            current = frontier.pop(0)
            if current in visited:
                continue
            visited.add(current)

            for edge in self._edges:
                if edge.source != current:
                    continue
                propagated = impacts[current] * edge.strength
                if propagated < 0.01:
                    continue
                existing = impacts.get(edge.target, 0.0)
                impacts[edge.target] = max(existing, propagated)
                if edge.target not in visited:
                    frontier.append(edge.target)

        return {k: round(v, 4) for k, v in impacts.items()}

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [
                {
                    "label": n.label,
                    "type": n.node_type,
                    "confidence": n.confidence,
                }
                for n in self._nodes.values()
            ],
            "edges": [
                {
                    "source": e.source,
                    "target": e.target,
                    "mechanism": e.mechanism,
                    "strength": e.strength,
                    "lag_hours": e.lag_hours,
                }
                for e in self._edges
            ],
        }

    @classmethod
    def from_macro_chain(cls, chain: dict[str, Any]) -> ShockChain:
        sc = cls()
        shock_source = chain.get("shockSource", "Unknown")
        sc.add_node(
            ShockNode(label=shock_source, node_type="shock_source", confidence=0.8)
        )

        for var in chain.get("macroVariables", []):
            sc.add_node(
                ShockNode(label=var, node_type="macro_variable", confidence=0.6)
            )
            sc.add_edge(
                ShockEdge(
                    source=shock_source,
                    target=var,
                    mechanism="direct_transmission",
                    strength=0.7,
                )
            )

        pricing = chain.get("marketPricing", "")
        if pricing:
            sc.add_node(
                ShockNode(
                    label="market_pricing", node_type="market_pricing", confidence=0.5
                )
            )
            for var in chain.get("macroVariables", [])[:2]:
                sc.add_edge(
                    ShockEdge(
                        source=var,
                        target="market_pricing",
                        mechanism="repricing",
                        strength=0.6,
                    )
                )

        allocation = chain.get("allocationImplication", "")
        if allocation:
            sc.add_node(
                ShockNode(label="allocation", node_type="allocation", confidence=0.4)
            )
            sc.add_edge(
                ShockEdge(
                    source="market_pricing" if pricing else shock_source,
                    target="allocation",
                    mechanism="portfolio_adjustment",
                    strength=0.5,
                )
            )

        return sc


__all__ = ["ShockChain", "ShockNode", "ShockEdge"]
