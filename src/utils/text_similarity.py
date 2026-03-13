from __future__ import annotations

from typing import Any


def generate_trigrams(text: str) -> set[str]:
    grams: set[str] = set()
    padded = f"  {text} "
    for idx in range(len(padded) - 2):
        grams.add(padded[idx : idx + 3])
    return grams


def jaccard_similarity(left: set[Any], right: set[Any]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    overlap = len(left & right)
    union = len(left | right)
    return overlap / union if union else 0.0


def dice_coefficient(left: set[Any], right: set[Any]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    overlap = len(left & right)
    return (2 * overlap) / (len(left) + len(right))


__all__ = [
    "dice_coefficient",
    "generate_trigrams",
    "jaccard_similarity",
]
