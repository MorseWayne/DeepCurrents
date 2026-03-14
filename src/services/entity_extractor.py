from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from ..config.settings import CONFIG

_gliner: Any = None

_DEFAULT_LABELS = [
    "person",
    "organization",
    "location",
    "asset",
    "currency",
    "index",
    "commodity",
    "central_bank",
    "country",
    "geopolitical_entity",
]


def _ensure_gliner() -> Any:
    global _gliner
    if _gliner is None:
        try:
            import gliner as _gl

            _gliner = _gl
        except ImportError:
            _gliner = False
            logger.debug("gliner not installed; GLiNER NER disabled")
    return _gliner


class EntityExtractor:
    def __init__(
        self,
        *,
        model_name: str | None = None,
        labels: list[str] | None = None,
        score_threshold: float = 0.5,
    ):
        self._model_name = model_name or CONFIG.gliner_model
        self._labels = labels or list(_DEFAULT_LABELS)
        self._score_threshold = score_threshold
        self._model: Any = None

    def _ensure_model(self) -> bool:
        if self._model is not None:
            return True
        gl = _ensure_gliner()
        if not gl:
            return False
        try:
            self._model = gl.GLiNER.from_pretrained(self._model_name)
            return True
        except Exception as exc:
            logger.warning(f"Failed to load GLiNER model {self._model_name}: {exc}")
            return False

    async def extract(
        self,
        text: str,
        labels: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if not text or not self._ensure_model():
            return []

        target_labels = labels or self._labels
        loop = asyncio.get_event_loop()
        try:
            raw_entities = await loop.run_in_executor(
                None,
                self._predict,
                text,
                target_labels,
            )
        except Exception as exc:
            logger.warning(f"GLiNER prediction failed: {exc}")
            return []

        return [
            {
                "text": ent.get("text", ""),
                "label": ent.get("label", ""),
                "score": round(float(ent.get("score", 0.0)), 3),
                "start": ent.get("start"),
                "end": ent.get("end"),
            }
            for ent in raw_entities
            if float(ent.get("score", 0.0)) >= self._score_threshold
        ]

    def _predict(self, text: str, labels: list[str]) -> list[dict[str, Any]]:
        return self._model.predict_entities(
            text, labels, threshold=self._score_threshold
        )


__all__ = ["EntityExtractor"]
